"""產物輸出：canonical NDJSON（git）+ v1 JSON artifacts（→ R2）+ manifest。

佈局（docs/DESIGN.md §4.5）：
  data/canonical/{term}/catalog.ndjson      一行一課（diff/審查/重建用）
  data/v1/terms/{term}/catalog.json         TermCatalog（web 主檔）
  data/v1/terms/{term}/classes.json         ClassDirectory
  data/v1/terms/{term}/periods.json         PeriodTable
  data/v1/terms/{term}/enrollment.json      EnrollmentLatest（volatile overlay）
  data/v1/terms/{term}/course/{id}.json     CourseDetail（逐週進度在 derive 即時計算）
  data/v1/manifest.json                     sha256/size/dataset_version＋來源新鮮度
  data/canonical/reports/{term}/weekly-progress.json   逐週進度精度報告（derive 產、commit 回 data branch）
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from models import (
    CALENDAR_SCHEMA_VERSION,
    CalendarManifestEntry,
    CatalogManifestEntry,
    CourseDetail,
    DetailsFreshness,
    SCHEMA_VERSION,
    CalendarEventsFeed,
    TermCalendarFile,
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
from ntut_catalog import enrollment_store, fetch_state
from ntut_catalog.orchestrator import TermResult
from ntut_catalog.parse_progress import attach_weekly_progress, progress_report
from ntut_catalog.periods import build_period_table
from ntut_catalog.pua import normalize_pua
from ntut_catalog.term_calendar import load_term

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


def derive(out_dir: Path) -> Manifest:
    """derive 層的唯一入口：canonical → 全新的 v1（spec §1 derive 規則）。

    - **確定性**：同一份 canonical → 逐位元組相同的 v1。不讀系統時間、不連網；
      manifest 的 `generated_at`／`published_at` 留空，由 publish 在上傳前寫入。
    - **先清空 `v1/`**：publish 以「本地 v1 有沒有這個檔」判斷 R2 上的物件是否過期，
      殘留的舊產物（例如已消失的課號）會讓它永遠刪不掉。v1 是純衍生物，重建即可。
    """
    v1 = out_dir / "v1"
    if v1.exists():
        shutil.rmtree(v1)
    return build_v1(out_dir, None)


def build_v1(out_dir: Path, generated_at: Optional[str] = None) -> Manifest:
    """從【全部】canonical 學期重建完整 v1（catalog/classes/periods/enrollment）+ manifest。

    catalog 純結構（無時間戳）；enrollment.json 取該學期最後一次觀測（enrollment_store.latest）；
    course/{id}.json 即時計算逐週進度；manifest 帶 fetch-state 的來源新鮮度。
    對外請用 `derive`（會先清空 v1/）；本函式保留給既有離線工具與測試。
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
        # 最新一次觀測 → enrollment.json overlay（spec §5：快照列不帶時間，
        # 頂層與每列的 observed_at 都填最後一筆觀測時間，web「人數更新於」語意不變）
        rows, observed = enrollment_store.latest(term_dir)
        counts = {
            r["offering_id"]: Enrollment(enrolled_count=r["enrolled_count"],
                                         withdrawn_count=r["withdrawn_count"],
                                         observed_at=observed)
            for r in rows
        }
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
            build_details_v1(out_dir, term, det, v1 / "course")
    # 課程標準（跨入學年，canonical/standards/*.json → v1/standards/）
    std_src = out_dir / "canonical" / "standards"
    if std_src.exists():
        std_dst = out_dir / "v1" / "standards"
        std_dst.mkdir(parents=True, exist_ok=True)
        for f in std_src.glob("*.json"):
            _write_v1_json(std_dst / f.name, f.read_text(encoding="utf-8"))
    # 行事曆事件（跨學期 top-level，canonical/calendar/ → v1/calendar/events.json）
    build_calendar_v1(out_dir, generated_at)
    # 學年度週次表（逐學期）。**刻意不放在上面那個 term 迴圈裡**——那個迴圈要求
    # canonical/{term}/catalog.ndjson 存在，但下一學期的週次表往往早於課程目錄就能產，
    # 綁在一起會讓「還沒開放查詢的下學期」拿不到週次表（#168 要的正是提前拿到）。
    build_term_calendars_v1(out_dir, generated_at)
    return write_manifest(out_dir, generated_at)


def build_details_v1(out_dir: Path, term: str, details_nd: Path, course_dir: Path) -> dict:
    """details.ndjson → course/{id}.json，並即時計算逐週進度（spec §4）。

    canonical 只存課綱原文；weekly_progress 是「原文 × 行事曆 × parser 版本」的衍生物，
    放在這裡算，行事曆改了或 parser 升版，下次 derive 自動生效，不必再記得手動重處理。
    沒有 calendar.json 的學期（110-1～114-2）→ `term=None`：日期／錨點規則停用，
    marker 路徑照常產出三態結果（Review Focus 4）。

    精度報告寫 `canonical/reports/{term}/weekly-progress.json`（不帶時間戳，數字不變就沒有 diff），
    由 commit-publish job 一併 commit——它的 commit 歷史就是長期精度追蹤。回傳報告。
    """
    term_obj = load_term(out_dir, term)
    course_dir.mkdir(parents=True, exist_ok=True)
    details = []
    for line in details_nd.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = CourseDetail.model_validate_json(line)
        attach_weekly_progress(d.syllabi, term_obj, course_name=d.name.zh)
        _write_v1_json(course_dir / f"{d.offering_id}.json", d.model_dump_json())
        details.append(d)
    report = progress_report(details, term, term_obj is not None)
    rp_dir = out_dir / "canonical" / "reports" / term
    rp_dir.mkdir(parents=True, exist_ok=True)
    (rp_dir / "weekly-progress.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return report


def build_calendar_v1(out_dir: Path, generated_at: str) -> bool:
    """canonical/calendar/{events.ndjson,meta.json} → v1/calendar/events.json。

    回傳有沒有產出（canonical 不存在時什麼都不做，讓沒跑過 crawl-calendar 的環境照常運作）。
    """
    src = out_dir / "canonical" / "calendar"
    nd, meta_path = src / "events.ndjson", src / "meta.json"
    if not (nd.exists() and meta_path.exists()):
        return False
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    # **刻意不帶 generated_at**（比照 catalog.json，見 structural_catalog）。
    # 帶建置時間戳會讓檔案每天都不同 → ETag 每天都變 → App 每天重抓 193 KB 拿不到 304。
    # 那正好抵消換源的理由之一（ics 自己沒有 ETag、直抓每次都是全量）。
    # 誠實的時間戳是 source.fetched_at（內容最後變動時間），它已經在 payload 裡，
    # 而且只在內容真的變動時才更新。
    feed = CalendarEventsFeed(
        source=meta["source"],
        horizon=meta["horizon"],
        events=[json.loads(line) for line in nd.read_text(encoding="utf-8").splitlines() if line.strip()],
    )
    dst = out_dir / "v1" / "calendar"
    dst.mkdir(parents=True, exist_ok=True)
    _write_v1_json(dst / "events.json", feed.model_dump_json())
    return True


def build_term_calendars_v1(out_dir: Path, generated_at: str) -> List[str]:
    """canonical/{term}/calendar.json → v1/terms/{term}/calendar.json。回傳處理過的學期。"""
    canonical = out_dir / "canonical"
    done: List[str] = []
    for term_dir in sorted(p for p in canonical.iterdir() if p.is_dir()) if canonical.exists() else []:
        src = term_dir / "calendar.json"
        if not src.exists():
            continue
        cal = TermCalendarFile.model_validate_json(src.read_text(encoding="utf-8"))
        cal.generated_at = None          # 同上：時間戳用 source.parsed_at，不用建置時間
        dst = out_dir / "v1" / "terms" / term_dir.name
        dst.mkdir(parents=True, exist_ok=True)
        _write_v1_json(dst / "calendar.json", cal.model_dump_json())
        done.append(term_dir.name)
    return done


def _calendar_content(calendar: TermCalendarFile) -> dict:
    """比對用的內容，**排除 parsed_at**——那是「這次解析的時間」，不是內容的一部分。"""
    return calendar.model_dump(exclude={"generated_at": True, "source": {"parsed_at"}})


def write_term_calendar(calendar: TermCalendarFile, term_key: str, out_dir: Path) -> bool:
    """**內容沒變就不重寫**——回傳 False。

    週次表一學期最多改一兩次，`Cache-Control` 因此設 max-age=86400。但原本每次跑都重寫，
    `source.parsed_at` 每天更新 → 檔案 bytes 每天不同 → ETag 每天失效 → App 每天重抓，
    那個長快取等於白設。這是 events.json 那個修正（#89）漏掉的另一半。

    修好之後 `parsed_at` 的語意才正確：**內容最後一次變動的時間**，不是最後一次跑的時間。
    """
    d = out_dir / "canonical" / term_key
    d.mkdir(parents=True, exist_ok=True)
    path = d / "calendar.json"
    if path.exists():
        previous = TermCalendarFile.model_validate_json(path.read_text(encoding="utf-8"))
        if _calendar_content(previous) == _calendar_content(calendar):
            return False
    path.write_text(calendar.model_dump_json(), encoding="utf-8")
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


def _entry(path: Path, rel_url: str, schema_version: int = SCHEMA_VERSION) -> ManifestEntry:
    data = path.read_bytes()
    return ManifestEntry(url=rel_url, sha256=hashlib.sha256(data).hexdigest(),
                         size=len(data), schema_version=schema_version)


def _academic_year(term_key: str) -> Optional[int]:
    try:
        return int(term_key.split("-")[0])
    except ValueError:
        return None


def _calendar_entries(out_dir: Path) -> Dict[str, CalendarManifestEntry]:
    """週次表的發現清單，限**已有週次表的學期之中「最新學年度＋前一學年度」**。

    為什麼要留前一學年度：每年 8/1 之後有一段期間新學年度的 ics 還沒匯入
    （112 學年度下學期拖到隔年 2 月），只留最新一年的話，剛匯入新學年度時 App 連剛結束
    那學期的週次表都拿不到。留前一年剛好填住這個洞，而且總數封頂在 4 筆、不會隨年份長大。

    範圍**由 canonical 內容決定、不讀系統時間**（spec §1 derive 確定性）。之前依建置日期
    推算當前學年度，同一份 canonical 在 7/31 與 8/1 建出不同的 manifest。改成以內容為準後，
    新學年度的 ics 一匯入（產出該年的 calendar.json），清單就自然往前移一年。
    舊的 calendar.json **檔案照舊留在 CDN**（derive 仍會產出，publish 不會當成過期刪掉），
    只是不列進清單——曾經存在是事實，但不該被發現。
    """
    terms_dir = out_dir / "v1" / "terms"
    paths = sorted(terms_dir.glob("*/calendar.json")) if terms_dir.exists() else []
    years = {y for y in (_academic_year(p.parent.name) for p in paths) if y is not None}
    if not years:
        return {}
    latest = max(years)
    keep = {latest, latest - 1}
    out: Dict[str, CalendarManifestEntry] = {}
    for path in paths:
        term_key = path.parent.name
        academic_year = _academic_year(term_key)
        if academic_year not in keep:
            continue
        weeks = (TermCalendarFile.model_validate_json(path.read_text(encoding="utf-8"))
                 .terms.get(term_key, None))
        if weeks is None or not weeks.weeks:
            continue
        base = _entry(path, f"terms/{term_key}/calendar.json", CALENDAR_SCHEMA_VERSION)
        out[term_key] = CalendarManifestEntry(
            **base.model_dump(),
            first_week_start=weeks.weeks[0].start,
            last_week_end=weeks.weeks[-1].end,
        )
    return out


def _catalog_entry(path: Path, rel_url: str) -> CatalogManifestEntry:
    """catalog 項目多帶 `count`（課數）——publish 的品質閘門以線上 manifest 的這個值為基準。"""
    base = _entry(path, rel_url)
    count = len(json.loads(path.read_bytes())["courses"])
    return CatalogManifestEntry(**base.model_dump(), count=count)


# 產物 → 來源資料集（spec §6）。enrollment.json 的來源是 catalog（daily 順帶記錄）與
# enrollment（選課季）兩個資料集——merge 讓兩者都寫 fetch-state 的同一個 `enrollment` 鍵
# （registry.ENROLLMENT_STATE_KEY），「取較新」已在那裡完成；不能拿 catalog 鍵來比，
# 它的 changed_at 是課程結構的變動時間，與人數無關。
_FRESHNESS_SOURCES = {
    "catalog": ("catalog",),
    "classes": ("catalog",),
    "enrollment": ("enrollment",),
    "mprograms": ("mprograms",),
    "calendar": ("calendar",),
}


def _latest_iso(values) -> Optional[str]:
    vals = [v for v in values if v]
    if not vals:
        return None
    return max(vals, key=lambda v: dt.datetime.fromisoformat(v))


def _freshness(state, datasets, term: Optional[str]) -> Dict[str, Optional[str]]:
    """從 fetch-state 取 checked_at／changed_at。calendar 無學期維度 → `_global`。"""
    entries = [fetch_state.get(state, ds, None if ds == "calendar" else term) for ds in datasets]
    entries = [e for e in entries if e]
    return {"checked_at": _latest_iso(e.get("checked_at") for e in entries),
            "changed_at": _latest_iso(e.get("changed_at") for e in entries)}


def _details_freshness(out_dir: Path, state, term: str) -> Optional[DetailsFreshness]:
    nd = out_dir / "canonical" / term / "details.ndjson"
    if not nd.exists():
        return None
    count = sum(1 for line in nd.read_text(encoding="utf-8").splitlines() if line.strip())
    return DetailsFreshness(**_freshness(state, ("details",), term), count=count)


def write_manifest(out_dir: Path, generated_at: Optional[str] = None) -> Manifest:
    """v1/manifest.json。來源新鮮度（checked_at／changed_at）讀 canonical 的 fetch-state，
    **不讀系統時間**——同一份 canonical（含 `_meta/`）→ 同一份 manifest。"""
    terms_dir = out_dir / "v1" / "terms"
    state = fetch_state.load(fetch_state.path_for(out_dir / "canonical"))
    terms = {}
    for term_dir in sorted(terms_dir.iterdir()) if terms_dir.exists() else []:
        if not term_dir.is_dir():
            continue
        term = term_dir.name
        files = {}
        for name in ["catalog", "classes", "periods", "enrollment", "mprograms", "calendar"]:
            p = term_dir / f"{name}.json"
            if p.exists():
                # calendar.json 走**獨立的** CALENDAR_SCHEMA_VERSION，不是全域那個。
                # 不區分的話 manifest 會說 schema_version=2 而檔案本身寫 1，
                # App decoder 對版本不符是整份拒收——會是靜默失效。
                if name == "catalog":
                    entry = _catalog_entry(p, f"terms/{term}/{name}.json")
                else:
                    entry = _entry(
                        p, f"terms/{term}/{name}.json",
                        CALENDAR_SCHEMA_VERSION if name == "calendar" else SCHEMA_VERSION)
                if name in _FRESHNESS_SOURCES:
                    entry = entry.model_copy(update=_freshness(state, _FRESHNESS_SOURCES[name], term))
                files[name] = entry
        if "catalog" not in files:
            continue
        # dataset_version = catalog.json 的結構 sha256（catalog 純結構→byte 穩定→版本穩定）
        terms[term] = ManifestTerm(
            catalog=files["catalog"],
            classes=files.get("classes"),
            periods=files.get("periods"),
            enrollment=files.get("enrollment"),
            mprograms=files.get("mprograms"),
            calendar=files.get("calendar"),
            details=_details_freshness(out_dir, state, term),
            dataset_version=files["catalog"].sha256,
        )
    calendar_freshness = _freshness(state, ("calendar",), None)
    calendars = {k: v.model_copy(update=calendar_freshness)
                 for k, v in _calendar_entries(out_dir).items()}
    manifest = Manifest(generated_at=generated_at, terms=terms, calendars=calendars)
    (out_dir / "v1" / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    return manifest
