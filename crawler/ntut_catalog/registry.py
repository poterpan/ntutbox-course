"""資料集登錄表：每個資料集**唯一**的宣告處（spec §2）。

新增資料集＝寫一個 fetcher＋v1 builder（artifacts.py）＋這裡一筆，**不新增 workflow 檔**：
workflow 依 cadence 分（daily／weekly／season），`pipeline --cadence X` 會跑這裡所有同頻率的
資料集；merge 依 `writes` 決定哪些檔可以進 data branch、依 `content` 算 fetch-state 的 hash。

fetcher 只包既有的爬取程式（orchestrator／detail／programs／calendar_events），**不重寫爬取
邏輯**，請求量與節流（client.py 的 0.4–0.8 秒間隔）與舊 CLI 完全相同。
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional, Sequence

from models import CourseOffering
from ntut_catalog import enrollment_store
from ntut_catalog.ics import TAIPEI
from ntut_catalog.nodes import NodeTally

logger = logging.getLogger(__name__)

Cadence = Literal["daily", "weekly", "season", "manual"]
TermRule = Literal["active", "current", "calendar", "none"]


@dataclass
class FetchOutput:
    """fetcher 的回報：實際寫出的檔（canonical 相對路徑）＋要交給 merge 的附帶資訊。

    明確回報而不是事後掃 mtime：行事曆這類「內容沒變就不重寫」的 fetcher 沒寫的檔，
    merge 就不會拿過期 checkout 裡的舊版本去覆寫最新 HEAD。
    """
    files: List[str] = field(default_factory=list)
    extra: Dict[str, object] = field(default_factory=dict)
    # 逐節點爬取的資料集（catalog／standards／mprograms／details）：重試後仍失敗、被跳過的節點
    # 與實際嘗試的節點數。fetcher 照舊續跑，由 merge 決定丟棄或從 HEAD 沿用（spec §3「節點失敗的處理」）。
    failed_nodes: List[Dict[str, object]] = field(default_factory=list)
    node_total: Optional[int] = None


class FetchContext:
    """fetcher 的執行環境。client 延遲建立（只跑行事曆時不必連學校）、測試可注入假的。"""

    def __init__(self, out_dir: Path,
                 catalog_client_factory: Optional[Callable[[], object]] = None,
                 calendar_client_factory: Optional[Callable[[], object]] = None,
                 now: Optional[Callable[[], dt.datetime]] = None):
        self.out_dir = out_dir
        self._catalog_factory = catalog_client_factory or _default_catalog_client
        self._calendar_factory = calendar_client_factory or _default_calendar_client
        self._now = now or (lambda: dt.datetime.now(TAIPEI))
        self._catalog = None
        self._calendar = None

    @property
    def canonical(self) -> Path:
        return self.out_dir / "canonical"

    def now_iso(self) -> str:
        return self._now().astimezone(TAIPEI).isoformat(timespec="seconds")

    def today(self) -> dt.date:
        return self._now().astimezone(TAIPEI).date()

    @property
    def catalog_client(self):
        if self._catalog is None:
            self._catalog = self._catalog_factory()
        return self._catalog

    @property
    def calendar_client(self):
        if self._calendar is None:
            self._calendar = self._calendar_factory()
        return self._calendar

    def rel(self, path: Path) -> str:
        return path.relative_to(self.canonical).as_posix()

    def close(self) -> None:
        for c in (self._catalog, self._calendar):
            if c is not None and hasattr(c, "close"):
                c.close()


def _default_catalog_client():
    from ntut_catalog.client import CatalogClient
    # 舊 CLI `--delay 0.5` → (0.4, 0.8)：與 client.py 的預設相同，節流不變。
    return CatalogClient()


def _default_calendar_client():
    from ntut_catalog.calendar_client import CalendarClient
    return CalendarClient()


@dataclass(frozen=True)
class Dataset:
    name: str
    cadence: Cadence
    terms: TermRule
    fetch: Callable[[FetchContext, Optional[str]], FetchOutput]  # (ctx, term_key)；無學期維度時為 None
    writes: tuple[str, ...]                     # canonical 相對路徑樣板（`{term}`、`*`）
    append_only: tuple[str, ...] = ()           # 由 merge 以「追加」方式合併的檔（不在 writes 覆寫）
    content: tuple[str, ...] = ()               # 算 fetch-state content_sha256 的內容檔樣板


# ------------------------------------------------------------------ 樣板比對

def expand(pattern: str, term: Optional[str]) -> str:
    """`{term}` 代入學期；無學期（多學期由 fetcher 決定）→ 萬用 `*`。"""
    return pattern.replace("{term}", term if term else "*")


def matches(rel: str, pattern: str) -> bool:
    """逐段 fnmatch（`*` 不跨 `/`）：`*/calendar.json` 不會誤中 `reports/x/calendar.json`。"""
    a, b = rel.split("/"), pattern.split("/")
    return len(a) == len(b) and all(fnmatch.fnmatchcase(x, y) for x, y in zip(a, b))


def matches_any(rel: str, patterns: Sequence[str], term: Optional[str]) -> bool:
    return any(matches(rel, expand(p, term)) for p in patterns)


def content_files(canonical: Path, ds: Dataset, term: Optional[str]) -> List[Path]:
    """canonical 中符合該資料集 `content` 樣板的檔（fetch-state hash 的輸入）。"""
    out = []
    for pattern in ds.content:
        out += [p for p in canonical.glob(expand(pattern, term))
                if p.is_file() and matches(p.relative_to(canonical).as_posix(), expand(pattern, term))]
    return sorted(set(out))


# ------------------------------------------------------------------ fetchers

def _catalog_term_dir(ctx: FetchContext, term: str) -> Path:
    return ctx.canonical / term


def fetch_calendar(ctx: FetchContext, term: Optional[str]) -> FetchOutput:
    """校網 ics → canonical/calendar/ ＋逐學期週次表（原 `crawl-calendar`）。

    學期由 fetcher 自決（當前學年度兩學期，`default_terms`）。內容沒變的檔不重寫、不回報。
    """
    from ntut_catalog.artifacts import (read_calendar_event_count, write_calendar_events,
                                        write_term_calendar)
    from ntut_catalog.calendar_client import ICS_URL
    from ntut_catalog.calendar_events import crawl_calendar_events
    from ntut_catalog.term_calendar import build_all_term_calendars, default_terms

    feed = crawl_calendar_events(ctx.calendar_client, ICS_URL,
                                 previous_count=read_calendar_event_count(ctx.out_dir))
    files: List[str] = []
    if write_calendar_events(feed, ctx.out_dir):
        files += ["calendar/events.ndjson", "calendar/meta.json"]
    calendars = build_all_term_calendars(feed.events, default_terms(ctx.today()),
                                         feed.source.url, feed.source.content_sha256)
    for key, cal in sorted(calendars.items()):
        if write_term_calendar(cal, key, ctx.out_dir):
            files.append(f"{key}/calendar.json")
    if not calendars:
        logger.warning("本次未產出任何週次表（新學年度尚未匯入）——既有的保留不動")
    if not feed.horizon.ok:
        # 告警但**不阻斷發布**——feed 沒有新學年不代表現有資料壞了。
        print(f"::warning title=行事曆 horizon 不足::feed 最遠只到 "
              f"{feed.horizon.max_start}，新學年度資料尚未匯入")
    logger.info("calendar: %d events, changed files: %s", len(feed.events), files or "無")
    return FetchOutput(files=files)


def fetch_catalog(ctx: FetchContext, term: str) -> FetchOutput:
    """課程目錄全量爬取（原 `crawl --force`）：catalog.ndjson＋classes.json＋候選人數快照。"""
    from ntut_catalog.artifacts import write_canonical
    from ntut_catalog.orchestrator import crawl_term

    observed_at = ctx.now_iso()
    result = crawl_term(ctx.catalog_client, term, observed_at)
    for w in result.warnings:
        logger.warning("[%s] %s", term, w)
    write_canonical(result, ctx.out_dir)
    snap = enrollment_store.write_candidate(
        _catalog_term_dir(ctx, term), enrollment_store.rows_from_enrollment(result.enrollment),
        observed_at)
    logger.info("[%s] catalog: %d courses, %d classes", term,
                len(result.catalog.courses), len(result.classes.classes))
    return FetchOutput(
        files=[f"{term}/catalog.ndjson", f"{term}/classes.json", ctx.rel(snap)],
        extra={"enrollment": {"observed_at": observed_at, "snapshot": snap.stem}},
        failed_nodes=result.failed_nodes, node_total=result.node_total,
    )


def fetch_enrollment(ctx: FetchContext, term: str) -> FetchOutput:
    """選課季輕量人數刷新（原 `refresh-enrollment`）：只抓人/撤，寫候選快照。"""
    from ntut_catalog.orchestrator import crawl_enrollment

    if not (_catalog_term_dir(ctx, term) / "catalog.ndjson").exists():
        raise RuntimeError(f"[{term}] no canonical catalog — 先跑 catalog 再刷人數")
    observed_at = ctx.now_iso()
    enr = crawl_enrollment(ctx.catalog_client, term, observed_at)
    snap = enrollment_store.write_candidate(
        _catalog_term_dir(ctx, term), enrollment_store.rows_from_enrollment(enr), observed_at)
    logger.info("[%s] enrollment: %d courses @ %s", term, len(enr.counts), observed_at)
    return FetchOutput(files=[ctx.rel(snap)],
                       extra={"enrollment": {"observed_at": observed_at, "snapshot": snap.stem}})


def fetch_mprograms(ctx: FetchContext, term: str) -> FetchOutput:
    from ntut_catalog.artifacts import write_mprograms
    from ntut_catalog.programs import crawl_mprograms

    tally = NodeTally()
    write_mprograms(crawl_mprograms(ctx.catalog_client, term, tally=tally), ctx.out_dir)
    return FetchOutput(files=[f"{term}/mprograms.json"],
                       failed_nodes=tally.failed, node_total=tally.total)


def fetch_details(ctx: FetchContext, term: str) -> FetchOutput:
    """課程描述＋教學大綱（原 `crawl-detail`）。只寫 canonical；逐週進度由 derive 算。"""
    from ntut_catalog.detail import crawl_detail, write_details

    cat_nd = _catalog_term_dir(ctx, term) / "catalog.ndjson"
    if not cat_nd.exists():
        raise RuntimeError(f"[{term}] no canonical catalog — 先跑 catalog 再爬詳情")
    offerings = [CourseOffering.model_validate_json(line)
                 for line in cat_nd.read_text(encoding="utf-8").splitlines() if line.strip()]
    logger.info("[%s] details: %d offerings ...", term, len(offerings))
    tally = NodeTally()
    details = crawl_detail(ctx.catalog_client, term, offerings, tally=tally)
    path = write_details(details, ctx.out_dir)
    if path is None:
        raise RuntimeError(f"[{term}] details 為空——不覆寫既有 canonical")
    with_syl = sum(1 for d in details if d.syllabi)
    logger.info("[%s] details: %d courses, %d 有大綱", term, len(details), with_syl)
    return FetchOutput(files=[ctx.rel(path)], failed_nodes=tally.failed, node_total=tally.total)


STANDARDS_YEARS_BACK = 5


def standards_years(today: dt.date) -> List[int]:
    """入學年＝當前學年度與前 5 學年（spec §2；大學部最長修業年限內的學生都涵蓋）。"""
    from ntut_catalog.term_calendar import current_academic_year
    ay = current_academic_year(today)
    return list(range(ay - STANDARDS_YEARS_BACK, ay + 1))


def fetch_standards(ctx: FetchContext, term: Optional[str]) -> FetchOutput:
    from ntut_catalog.artifacts import write_standards
    from ntut_catalog.programs import crawl_standards

    files = []
    tally = NodeTally()   # 全部入學年共用一份：standards 是一筆 (資料集, _global)，比例也整筆算
    for year in standards_years(ctx.today()):
        write_standards(crawl_standards(ctx.catalog_client, year, tally=tally), ctx.out_dir)
        files.append(f"standards/{year}.json")
    return FetchOutput(files=files, failed_nodes=tally.failed, node_total=tally.total)


_ENROLLMENT_SNAPSHOTS = "{term}/enrollment/*.ndjson"
_OBSERVATIONS = "{term}/enrollment/" + enrollment_store.OBSERVATIONS

DATASETS: Dict[str, Dataset] = {d.name: d for d in [
    Dataset("calendar", "daily", "calendar", fetch_calendar,
            writes=("calendar/events.ndjson", "calendar/meta.json", "{term}/calendar.json"),
            content=("calendar/events.ndjson", "calendar/meta.json", "{term}/calendar.json")),
    Dataset("catalog", "daily", "active", fetch_catalog,
            writes=("{term}/catalog.ndjson", "{term}/classes.json", _ENROLLMENT_SNAPSHOTS),
            append_only=(_OBSERVATIONS,),
            # catalog 的 hash **不含** enrollment（Fable P1-5）：人數每次都變，含進來
            # catalog 的 changed_at 就失去意義。enrollment 另為 fetch-state 的 `enrollment` 鍵。
            content=("{term}/catalog.ndjson", "{term}/classes.json")),
    Dataset("mprograms", "daily", "active", fetch_mprograms,
            writes=("{term}/mprograms.json",), content=("{term}/mprograms.json",)),
    Dataset("details", "weekly", "current", fetch_details,
            writes=("{term}/details.ndjson",), content=("{term}/details.ndjson",)),
    Dataset("standards", "weekly", "none", fetch_standards,
            writes=("standards/*.json",), content=("standards/*.json",)),
    Dataset("enrollment", "season", "current", fetch_enrollment,
            writes=(_ENROLLMENT_SNAPSHOTS,), append_only=(_OBSERVATIONS,)),
]}

# fetch-state 裡 enrollment 的鍵：catalog 與 enrollment 兩個資料集都會寫人數快照，共用這一格。
ENROLLMENT_STATE_KEY = "enrollment"


def for_cadence(cadence: str) -> List[Dataset]:
    return [d for d in DATASETS.values() if d.cadence == cadence]


# ------------------------------------------------------------------ 學期規則

def resolve_terms(rule: TermRule, explicit: Sequence[str],
                  current: Callable[[], str],
                  active_env: Optional[str] = None) -> List[Optional[str]]:
    """學期規則集中實作（取代 6 份 workflow 內的 shell）。

    - 有學期維度（active／current）且明確指定 `explicit` → 一律用指定的。
    - `active`  = repo var `ACTIVE_TERMS`（經 env 注入，可用範圍語法），未設則同 `current`。
    - `current` = `current-term` 偵測結果（QueryCurrPage 預設學期；12 月 115-2 選課期間
      它可能仍是 115-1——所以 season 的 terms 必填，由 pipeline 把關）。
    - `calendar`／`none` → `[None]`：跑一次、fetch-state 用 `_global` 鍵；行事曆的學期由 fetcher 自決。
    """
    from ntut_catalog.cli import expand_terms

    if rule in ("calendar", "none"):
        return [None]
    if explicit:
        return list(explicit)
    if rule == "active":
        raw = os.environ.get("ACTIVE_TERMS", "") if active_env is None else active_env
        if raw.strip():
            return list(expand_terms(raw.strip()))
    return [current()]


# ------------------------------------------------------------------ commit 範圍

# 登錄表以外、commit-publish job 也要 commit 的檔：fetch-state（merge 寫）與逐週進度報告（derive 寫）。
_EXTRA_COMMITTED = ("_meta/fetch-state.json", "reports/{term}/weekly-progress.json")


def committable(rel: str) -> bool:
    """data branch 相對路徑是否在 commit 範圍內（spec §2：`git add` 範圍由登錄表 `writes` 產生，
    workflow 內不再手寫 glob）。學期一律當萬用——commit 的是合併後的整棵 canonical。"""
    patterns = [p for ds in DATASETS.values() for p in ds.writes + ds.append_only]
    return matches_any(rel, patterns + list(_EXTRA_COMMITTED), None)
