"""一次性遷移：舊 canonical → 管線 v2 形狀（spec §7）。**切換完成、驗證後於下一個 PR 刪除。**

  python -m ntut_catalog migrate-pipeline-v2 --data data/canonical

`--data` 是 data branch 的 checkout（canonical 根目錄，要是 git 工作區——fetch-state 的時間
取自 git log）。四步，全部**冪等**（跑第二次＝什麼都不動）：

  1. `{t}/details.ndjson`：去掉 `generated_at` 與每份 syllabus 的 `weekly_progress`
     （逐週進度改在 derive 即時計算，spec §4）。以新版 `detail_line` 重新序列化——
     之後 fetch 寫出的位元組與遷移結果一致，第一次重爬不會因格式不同而整份變動。
  2. `{t}/enrollment/`：舊檔（`YYYY-MM-DD`／`YYYY-MM-DDTHH`，列內帶 `observed_at`）→
     `YYYY-MM-DDTHHMM.ndjson`。檔名取**列內** `observed_at`（不用 git log：日檔是原地覆寫，
     首次 commit 時間不代表現存內容）；列內去掉 `observed_at`、依課號排序（與
     `enrollment_store.rows_from_enrollment` 相同，「內容相同」＝「位元組相同」）；與時間上
     前一份內容相同者刪除；每個原檔各一筆觀測重建 `observations.ndjson`。
  3. `_meta/fetch-state.json`（已存在就不動）：每個 (資料集, 學期) 的時間取自 git log
     （見 `_init_fetch_state`），`content_sha256` 與 merge 的算法相同（`registry.content_files`
     ＋`fetch_state.content_hash`）——遷移後第一次 merge 看到上游沒變，hash 就對得上。
  4. `reports/*/weekly-progress.json`：去掉 `generated_at`。
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from models import CourseDetail
from ntut_catalog import enrollment_store, fetch_state, registry
from ntut_catalog.detail import detail_line
from ntut_catalog.ics import TAIPEI

logger = logging.getLogger(__name__)

_TERM_RE = re.compile(r"^\d{3}-[123]$")

# (dataset, term) → 最後 commit 時間（ISO，+08:00）。測試可注入。
GitTime = Callable[[Path, Sequence[Path]], Optional[str]]


@dataclass
class MigrationSummary:
    details_files: List[str] = field(default_factory=list)       # 有改寫的 details.ndjson
    enrollment_terms: Dict[str, Dict[str, int]] = field(default_factory=dict)
    fetch_state: str = "skipped"                                  # created／exists
    fetch_state_entries: int = 0
    reports_files: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.details_files or self.enrollment_terms or self.reports_files
                    or self.fetch_state == "created")

    def to_json(self) -> dict:
        d = asdict(self)
        d["changed"] = self.changed
        return d


def git_last_commit_time(repo: Path, paths: Sequence[Path]) -> Optional[str]:
    """這些檔最後一次 commit 的時間（committer date，換成台北時間）。沒有紀錄 → None。"""
    if not paths:
        return None
    rels = [p.relative_to(repo).as_posix() for p in paths]
    out = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%cI", "--", *rels],
                         check=True, capture_output=True, text=True).stdout.strip()
    if not out:
        return None
    return dt.datetime.fromisoformat(out).astimezone(TAIPEI).isoformat(timespec="seconds")


def _term_dirs(canonical: Path) -> List[Path]:
    return sorted(p for p in canonical.iterdir() if p.is_dir() and _TERM_RE.match(p.name))


# ------------------------------------------------------------------ 1. details

def migrate_details(path: Path) -> bool:
    """去 `generated_at`／`weekly_progress`，以新版格式重寫。回傳是否改動。"""
    old = path.read_text(encoding="utf-8")
    lines = []
    for line in old.splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        d.pop("generated_at", None)
        for s in d.get("syllabi") or []:
            s.pop("weekly_progress", None)
        lines.append(detail_line(CourseDetail.model_validate(d)) + "\n")
    new = "".join(lines)
    if new == old:
        return False
    path.write_text(new, encoding="utf-8")
    return True


# ------------------------------------------------------------------ 2. enrollment

def _legacy_snapshots(enr_dir: Path) -> List[Path]:
    """舊格式快照：`*.ndjson` 中不是觀測紀錄、檔名也不是 `YYYY-MM-DDTHHMM` 者。"""
    return sorted(p for p in enr_dir.glob("*.ndjson")
                  if p.name != enrollment_store.OBSERVATIONS
                  and not enrollment_store._STAMP_RE.match(p.stem))


def _snapshot_text(rows: List[dict]) -> str:
    clean = sorted(({"offering_id": r["offering_id"], "enrolled_count": r["enrolled_count"],
                     "withdrawn_count": r["withdrawn_count"]} for r in rows),
                   key=lambda r: r["offering_id"])
    return enrollment_store._dump_rows(clean)


def migrate_enrollment(term_dir: Path, warnings: List[str]) -> Optional[Dict[str, int]]:
    """重新命名＋去時間戳＋去重＋重建觀測紀錄。沒有舊檔（已遷移或無人數）→ None。"""
    enr_dir = term_dir / "enrollment"
    if not enr_dir.exists():
        return None
    legacy = _legacy_snapshots(enr_dir)
    if not legacy:
        return None
    if (enr_dir / enrollment_store.OBSERVATIONS).exists() or enrollment_store.snapshots(term_dir):
        raise RuntimeError(f"{enr_dir}: 新舊格式混在一起（已有 observations／新檔名又有舊檔），"
                           "不自動處理，請人工確認")

    items = []   # (observed_at datetime, observed_at 原字串, 舊檔, 快照文字)
    for p in legacy:
        rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        stamps = {r.get("observed_at") for r in rows}
        stamps.discard(None)
        if not stamps:
            raise RuntimeError(f"{p}: 列內沒有 observed_at，無法決定新檔名")
        if len(stamps) > 1:
            warnings.append(f"{p.relative_to(term_dir.parent)}: 列內 observed_at 不一致"
                            f"（{len(stamps)} 種），取最晚者")
        observed = max(stamps, key=dt.datetime.fromisoformat)
        items.append((dt.datetime.fromisoformat(observed), observed, p, _snapshot_text(rows)))
    items.sort(key=lambda x: x[0])

    kept: Dict[str, str] = {}      # 新檔名 → 內容
    observations = []
    last_name: Optional[str] = None
    for _, observed, _, text in items:
        if last_name is not None and kept[last_name] == text:
            observations.append((observed, last_name))       # 與前一份相同：不另存快照
            continue
        t = dt.datetime.strptime(enrollment_store.stamp_of(observed), enrollment_store._STAMP_FMT)
        while t.strftime(enrollment_store._STAMP_FMT) in kept:   # 同一分鐘不同內容：往後找空位
            t += dt.timedelta(minutes=1)
        name = t.strftime(enrollment_store._STAMP_FMT)
        kept[name] = text
        observations.append((observed, name))
        last_name = name

    for name, text in kept.items():
        (enr_dir / f"{name}.ndjson").write_text(text, encoding="utf-8")
    for _, _, p, _ in items:
        p.unlink()
    (enr_dir / enrollment_store.OBSERVATIONS).write_text(
        "".join(json.dumps({"observed_at": o, "snapshot": n}, ensure_ascii=False) + "\n"
                for o, n in observations), encoding="utf-8")
    return {"legacy_files": len(items), "snapshots": len(kept), "observations": len(observations)}


# ------------------------------------------------------------------ 3. fetch-state

def _writes_files(canonical: Path, ds: registry.Dataset, term: Optional[str]) -> List[Path]:
    out = set()
    for pattern in ds.writes:
        pat = registry.expand(pattern, term)
        out |= {p for p in canonical.glob(pat)
                if p.is_file() and registry.matches(p.relative_to(canonical).as_posix(), pat)}
    return sorted(out)


def _collect_times(canonical: Path, git_time: GitTime) -> Dict[tuple, Dict[str, Optional[str]]]:
    """**遷移改檔之前**先查 git log：enrollment 舊檔改名後，新檔名在 git 裡沒有歷史。

    - `changed_at`＝內容檔（登錄表 `content`）最後 commit 時間；
    - `checked_at`＝該資料集全部 `writes` 檔最後 commit 時間（≥ changed_at）。catalog 的
      writes 含每日的人數快照——舊流程每天都會爬 catalog，但課程結構沒變就不 commit
      catalog.ndjson，只有人數那個 commit 能證明「那天確認過」。
    """
    times: Dict[tuple, Dict[str, Optional[str]]] = {}
    terms = [t.name for t in _term_dirs(canonical)]
    for ds in registry.DATASETS.values():
        if not ds.content:
            continue
        for term in ([None] if ds.terms in ("calendar", "none") else terms):
            content = registry.content_files(canonical, ds, term)
            if not content:
                continue
            changed = git_time(canonical, content)
            checked = git_time(canonical, _writes_files(canonical, ds, term)) or changed
            times[(ds.name, term)] = {"checked_at": checked, "changed_at": changed}
    return times


def _init_fetch_state(canonical: Path, times, warnings: List[str]) -> fetch_state.FetchState:
    state = fetch_state.empty()
    for (name, term), t in sorted(times.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        if t["changed_at"] is None:
            warnings.append(f"fetch-state {name}/{term or fetch_state.GLOBAL}: "
                            "內容檔沒有 git 紀錄，略過")
            continue
        ds = registry.DATASETS[name]
        digest = fetch_state.content_hash(registry.content_files(canonical, ds, term), canonical)
        fetch_state.update(state, name, term, digest, t["checked_at"], changed_at=t["changed_at"])
    # enrollment 鍵（catalog 與 enrollment 資料集共用）：與 merge 的 `_update_enrollment_state`
    # 同算法——hash＝最新一份快照、changed_at＝該快照檔名的時間；checked_at＝最後一筆觀測。
    for term_dir in _term_dirs(canonical):
        snaps = enrollment_store.snapshots(term_dir)
        obs = enrollment_store.observations(term_dir)
        if not snaps or not obs:
            continue
        newest = term_dir / "enrollment" / f"{snaps[-1]}.ndjson"
        fetch_state.update(state, registry.ENROLLMENT_STATE_KEY, term_dir.name,
                           fetch_state.content_hash([newest], canonical),
                           obs[-1]["observed_at"],
                           changed_at=enrollment_store.stamp_to_iso(snaps[-1]))
    return state


# ------------------------------------------------------------------ 4. reports

def migrate_report(path: Path) -> bool:
    old = path.read_text(encoding="utf-8")
    data = json.loads(old)
    if "generated_at" not in data:
        return False
    data.pop("generated_at")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


# ------------------------------------------------------------------ 入口

def migrate(canonical: Path, git_time: GitTime = git_last_commit_time) -> MigrationSummary:
    canonical = canonical.resolve()
    summary = MigrationSummary()
    state_path = fetch_state.path_for(canonical)
    need_state = not state_path.exists()
    times = _collect_times(canonical, git_time) if need_state else {}

    for term_dir in _term_dirs(canonical):
        det = term_dir / "details.ndjson"
        if det.exists() and migrate_details(det):
            summary.details_files.append(det.relative_to(canonical).as_posix())
        stats = migrate_enrollment(term_dir, summary.warnings)
        if stats:
            summary.enrollment_terms[term_dir.name] = stats

    if need_state:
        state = _init_fetch_state(canonical, times, summary.warnings)
        fetch_state.save(state_path, state)
        summary.fetch_state = "created"
        summary.fetch_state_entries = sum(len(v) for v in state["datasets"].values())
    else:
        summary.fetch_state = "exists"

    reports = canonical / "reports"
    for p in sorted(reports.glob("*/weekly-progress.json")) if reports.exists() else []:
        if migrate_report(p):
            summary.reports_files.append(p.relative_to(canonical).as_posix())
    return summary
