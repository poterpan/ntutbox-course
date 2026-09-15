"""產物輸出：canonical NDJSON（git）+ v1 JSON artifacts（→ R2）+ manifest。

佈局（docs/DESIGN.md §4.5）：
  data/canonical/{term}/catalog.ndjson      一行一課（diff/審查/重建用）
  data/v1/terms/{term}/catalog.json         TermCatalog（web 主檔）
  data/v1/terms/{term}/classes.json         ClassDirectory
  data/v1/terms/{term}/periods.json         PeriodTable
  data/v1/terms/{term}/enrollment.json      EnrollmentLatest（volatile overlay）
  data/v1/manifest.json                     sha256/size/dataset_version
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from models import (
    CalendarEventsFeed,
    CourseOffering,
    Enrollment,
    EnrollmentLatest,
    Freshness,
    Manifest,
    ManifestEntry,
    ManifestTerm,
    TermCatalog,
    TermInfo,
)
from ntut_catalog.orchestrator import TermResult
from ntut_catalog.periods import build_period_table
from ntut_catalog.pua import normalize_pua

# normalize.py 寫入 raw_fields 的 volatile 鍵（人數/撤選），結構檔需剔除以免每日 churn
_VOLATILE_RAW_KEYS = ("enrolled", "withdrawn")


def _write_v1_json(path: Path, text: str) -> None:
    """寫出 v1 JSON：先做 PUA 正規化（canonical 不動，只有消費層 v1 修）。

    PUA 碼位只出現在字串值、不會落在 JSON 結構字元，且本 repo 序列化一律不 \\u 轉義
    （model_dump_json / json.dumps(ensure_ascii=False) 皆直出 raw UTF-8）→ 對序列化文字
    做碼位替換與對物件遞迴替換等價，且保留原位元組格式（僅 PUA→真字處位元組改變）。
    """
    path.write_text(normalize_pua(text), encoding="utf-8")


def structural_course(c: CourseOffering) -> CourseOffering:
    """回傳去掉 volatile enrollment（含 raw_fields 人數欄）的課程副本，**不 mutate 原物件**。"""
    s = c.model_copy(deep=True)
    s.enrollment = Enrollment()  # 全 None；capacity 本即 None
    s.raw_fields = {k: v for k, v in s.raw_fields.items() if k not in _VOLATILE_RAW_KEYS}
    return s


def structural_catalog(cat: TermCatalog) -> TermCatalog:
    """回傳純結構 catalog：去爬取時間戳 + 每課去 volatile，**不 mutate 原物件**。"""
    s = cat.model_copy(deep=True)
    s.generated_at = None
    s.freshness = Freshness()
    s.courses = [structural_course(c) for c in s.courses]
    return s


def write_canonical(result: TermResult, out_dir: Path) -> None:
    """寫 canonical（git 真相）：結構化 catalog.ndjson + classes.json。"""
    term = result.catalog.term.key
    d = out_dir / "canonical" / term
    d.mkdir(parents=True, exist_ok=True)
    with (d / "catalog.ndjson").open("w", encoding="utf-8") as f:
        for course in result.catalog.courses:
            f.write(structural_course(course).model_dump_json(exclude_none=False) + "\n")
    (d / "classes.json").write_text(result.classes.model_dump_json(), encoding="utf-8")


def write_enrollment_snapshot(term_key: str, enrollment, out_dir: Path, date: str) -> None:
    """寫 enrollment 時序快照：offering_id + 人數/撤選 + observed_at。

    date 顆粒由呼叫端決定：daily 用 'YYYY-MM-DD'；選課季 hourly 用 'YYYY-MM-DDTHH'
    （同顆粒重跑覆寫同檔 → 限制檔數）。enrollment 為 EnrollmentLatest。
    """
    d = out_dir / "canonical" / term_key / "enrollment"
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{date}.ndjson").open("w", encoding="utf-8") as f:
        for oid, e in enrollment.counts.items():
            f.write(
                json.dumps(
                    {
                        "offering_id": oid,
                        "enrolled_count": e.enrolled_count,
                        "withdrawn_count": e.withdrawn_count,
                        "observed_at": e.observed_at,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def build_v1(out_dir: Path, generated_at: str) -> Manifest:
    """從【全部】canonical 學期重建完整 v1（catalog/classes/periods/enrollment）+ manifest。

    catalog 純結構（無時間戳）；enrollment.json 取該學期【最新】snapshot 還原數字。
    """
    canonical = out_dir / "canonical"
    periods_json = build_period_table().model_dump_json()
    for term_dir in sorted(p for p in canonical.iterdir() if p.is_dir()) if canonical.exists() else []:
        term = term_dir.name
        cat_nd = term_dir / "catalog.ndjson"
        if not cat_nd.exists():
            continue
        year, sem = int(term.split("-")[0]), int(term.split("-")[1])
        courses = [
            CourseOffering.model_validate_json(line)
            for line in cat_nd.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        catalog = TermCatalog(
            term=TermInfo(key=term, year=year, semester=sem, label=f"{year} 學年度第 {sem} 學期"),
            generated_at=None,
            courses=courses,
        )
        v1 = out_dir / "v1" / "terms" / term
        v1.mkdir(parents=True, exist_ok=True)
        _write_v1_json(v1 / "catalog.json", catalog.model_dump_json())
        # names 索引（邊緣 OG 用；課號→中文課名，小檔、隨 cron 自動發，新學期零介入）
        names = {c.offering_id: c.name.zh for c in courses if c.name and c.name.zh}
        _write_v1_json(
            v1 / "names.json",
            json.dumps(names, ensure_ascii=False, separators=(",", ":")),
        )
        _write_v1_json(v1 / "classes.json", (term_dir / "classes.json").read_text(encoding="utf-8"))
        _write_v1_json(v1 / "periods.json", periods_json)
        # 最新 snapshot → enrollment.json overlay
        snaps = sorted((term_dir / "enrollment").glob("*.ndjson")) if (term_dir / "enrollment").exists() else []
        counts: dict = {}
        observed = None
        if snaps:
            for line in snaps[-1].read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                counts[r["offering_id"]] = Enrollment(
                    enrolled_count=r["enrolled_count"],
                    withdrawn_count=r["withdrawn_count"],
                    observed_at=r["observed_at"],
                )
                observed = r["observed_at"]
        _write_v1_json(
            v1 / "enrollment.json",
            EnrollmentLatest(term_key=term, observed_at=observed, counts=counts).model_dump_json(),
        )
        # 選用：微學程（canonical/{term}/mprograms.json 存在才複製）
        mp = term_dir / "mprograms.json"
        if mp.exists():
            _write_v1_json(v1 / "mprograms.json", mp.read_text(encoding="utf-8"))
        # 選用：詳情（canonical/{term}/details.ndjson 存在 → 炸成 course/{id}.json）
        det = term_dir / "details.ndjson"
        if det.exists():
            cdir = v1 / "course"
            cdir.mkdir(exist_ok=True)
            for line in det.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                oid = json.loads(line)["offering_id"]
                _write_v1_json(cdir / f"{oid}.json", line)
    # 課程標準（跨入學年，canonical/standards/*.json → v1/standards/）
    std_src = out_dir / "canonical" / "standards"
    if std_src.exists():
        std_dst = out_dir / "v1" / "standards"
        std_dst.mkdir(parents=True, exist_ok=True)
        for f in std_src.glob("*.json"):
            _write_v1_json(std_dst / f.name, f.read_text(encoding="utf-8"))
    # 行事曆事件（跨學期 top-level，canonical/calendar/ → v1/calendar/events.json）
    build_calendar_v1(out_dir, generated_at)
    return write_manifest(out_dir, generated_at)


def build_calendar_v1(out_dir: Path, generated_at: str) -> bool:
    """canonical/calendar/{events.ndjson,meta.json} → v1/calendar/events.json。

    回傳有沒有產出（canonical 不存在時什麼都不做，讓沒跑過 crawl-calendar 的環境照常運作）。
    """
    src = out_dir / "canonical" / "calendar"
    nd, meta_path = src / "events.ndjson", src / "meta.json"
    if not (nd.exists() and meta_path.exists()):
        return False
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    feed = CalendarEventsFeed(
        generated_at=generated_at,
        source=meta["source"],
        horizon=meta["horizon"],
        events=[json.loads(line) for line in nd.read_text(encoding="utf-8").splitlines() if line.strip()],
    )
    dst = out_dir / "v1" / "calendar"
    dst.mkdir(parents=True, exist_ok=True)
    _write_v1_json(dst / "events.json", feed.model_dump_json())
    return True


def write_mprograms(directory, out_dir: Path) -> None:
    d = out_dir / "canonical" / directory.term_key
    d.mkdir(parents=True, exist_ok=True)
    (d / "mprograms.json").write_text(directory.model_dump_json(), encoding="utf-8")


def write_standards(directory, out_dir: Path) -> None:
    d = out_dir / "canonical" / "standards"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{directory.entry_year}.json").write_text(directory.model_dump_json(), encoding="utf-8")


def write_calendar_events(feed: CalendarEventsFeed, out_dir: Path) -> bool:
    """canonical/calendar/：events.ndjson（一行一事件、穩定排序）+ meta.json（provenance）。

    **內容沒變就不重寫**——回傳 False。理由：抓取是每日跑的，但行事曆一年只動幾次；
    每天重寫會在 data branch 產生無意義的 commit，把「行事曆改了什麼」這條免費稽核軌跡
    淹沒在噪音裡。判斷依據是正規化後的 content_sha256，不是檔案 md5（VEVENT 順序不穩）。
    """
    d = out_dir / "canonical" / "calendar"
    d.mkdir(parents=True, exist_ok=True)
    meta_path = d / "meta.json"
    if meta_path.exists():
        prev = json.loads(meta_path.read_text(encoding="utf-8"))
        if prev.get("source", {}).get("content_sha256") == feed.source.content_sha256:
            return False
    (d / "events.ndjson").write_text(
        "".join(e.model_dump_json() + "\n" for e in feed.events), encoding="utf-8"
    )
    meta_path.write_text(
        json.dumps({"source": feed.source.model_dump(), "horizon": feed.horizon.model_dump()},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    return True


def read_calendar_event_count(out_dir: Path) -> int:
    """既有 canonical 的事件筆數，給空結果/殘缺防呆當比較基準。不存在回 0。"""
    nd = out_dir / "canonical" / "calendar" / "events.ndjson"
    if not nd.exists():
        return 0
    return sum(1 for line in nd.read_text(encoding="utf-8").splitlines() if line.strip())


def _entry(path: Path, rel_url: str) -> ManifestEntry:
    data = path.read_bytes()
    return ManifestEntry(url=rel_url, sha256=hashlib.sha256(data).hexdigest(), size=len(data))


def write_manifest(out_dir: Path, generated_at: str) -> Manifest:
    terms_dir = out_dir / "v1" / "terms"
    terms = {}
    for term_dir in sorted(terms_dir.iterdir()) if terms_dir.exists() else []:
        if not term_dir.is_dir():
            continue
        term = term_dir.name
        files = {}
        for name in ["catalog", "classes", "periods", "enrollment", "mprograms"]:
            p = term_dir / f"{name}.json"
            if p.exists():
                files[name] = _entry(p, f"terms/{term}/{name}.json")
        if "catalog" not in files:
            continue
        # dataset_version = catalog.json 的結構 sha256（catalog 純結構→byte 穩定→版本穩定）
        terms[term] = ManifestTerm(
            catalog=files["catalog"],
            classes=files.get("classes"),
            periods=files.get("periods"),
            enrollment=files.get("enrollment"),
            mprograms=files.get("mprograms"),
            dataset_version=files["catalog"].sha256,
        )
    manifest = Manifest(generated_at=generated_at, terms=terms)
    (out_dir / "v1" / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    return manifest
