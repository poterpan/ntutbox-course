"""學年度週次表（契約三）：推導規則、關鍵字唯一性、10 條不變量、10 學期回歸。

這裡的整合測試打的是版控裡的 2026-09-14 ics 快照與 115 學年度人工核對快照，離線、不碰網路。
"""
import datetime as dt
import json
from pathlib import Path

import pytest

from models import AcademicTerm, DateRange, TermWeek
from ntut_catalog.calendar_events import parse_calendar_events
from ntut_catalog.term_calendar import (
    CalendarDerivationError,
    build_all_term_calendars,
    check_invariants,
    check_window_invariants,
    current_academic_year,
    default_terms,
    derive_term,
    derive_weeks,
    load_week_table_reference,
    pick_event,
    saturday_on_or_before,
    sunday_on_or_before,
    term_window,
    verify_week_table_regression,
)

REPO = Path(__file__).resolve().parents[2]
SNAPSHOT_ICS = (REPO / "docs" / "research" / "assets" / "2026-09-16-calendar-ics-evaluation"
                / "raw" / "gcal-basic.ics")
SNAPSHOT_115 = Path(__file__).parent / "fixtures" / "term-calendar-115-snapshot.json"
D = dt.date.fromisoformat


@pytest.fixture(scope="module")
def events():
    return parse_calendar_events(SNAPSHOT_ICS.read_text(encoding="utf-8"),
                                 today=dt.date(2026, 9, 16)).events


# ----------------------------------------------------------------- 推導規則

def test_term_window():
    assert term_window("115-1") == (D("2026-08-01"), D("2027-01-31"))
    assert term_window("115-2") == (D("2027-02-01"), D("2027-07-31"))


def test_summer_term_has_no_week_table():
    with pytest.raises(CalendarDerivationError, match="暑期"):
        term_window("115-3")


@pytest.mark.parametrize("day,expected", [
    ("2026-09-07", "2026-09-06"),   # 週一 → 前一個週日
    ("2026-09-06", "2026-09-06"),   # 本身是週日 → 自己
    ("2026-09-12", "2026-09-06"),   # 週六 → 同週週日
])
def test_sunday_on_or_before(day, expected):
    assert sunday_on_or_before(D(day)) == D(expected)


def test_saturday_on_or_before():
    assert saturday_on_or_before(D("2027-01-10")) == D("2027-01-09")   # 週日 → 前一天週六
    assert saturday_on_or_before(D("2027-01-09")) == D("2027-01-09")   # 本身週六


def test_derive_weeks_anchors_week_one_on_instruction_day():
    """第 1 週 = 開學日所在的那一週（週日起算）。PDF 把再前一週標「準備」、不給編號——
    這條專抓「開學日 + 7×(N-1)」那個經典錯誤（每個週日都會差一週）。"""
    weeks = derive_weeks(D("2026-09-07"), D("2027-01-11"))
    assert len(weeks) == 18
    assert (weeks[0].number, weeks[0].start, weeks[0].end) == (1, "2026-09-06", "2026-09-12")
    assert (weeks[-1].number, weeks[-1].end) == (18, "2027-01-09")
    assert all(D(w.start).weekday() == 6 for w in weeks)


def test_week_count_is_derived_not_hardcoded():
    """縮短學期 → 週數跟著變。18 是算出來的結果，不是寫死的常數。"""
    assert len(derive_weeks(D("2026-09-07"), D("2026-12-14"))) == 14


# ----------------------------------------------------------------- 關鍵字唯一性（不變量⑧）

def test_pick_event_requires_exactly_one(events):
    window = [e for e in events if "2026-09" <= (e.start_date or "") <= "2026-10"]
    with pytest.raises(CalendarDerivationError, match="找不到"):
        pick_event(window, "115-1", (r"絕對不存在的關鍵字", None))


def test_pick_event_returns_none_for_optional_miss(events):
    assert pick_event(events, "115-1", (r"絕對不存在的關鍵字", None), required=False) is None


def test_pick_event_aborts_on_ambiguity():
    """**不得靜默取第一筆**——那等於在來源措辭改變時悄悄猜一個答案，
    而週次表錯了 App 整學期都是錯的。"""
    from models import CalendarEvent
    two = [CalendarEvent(uid=str(i), summary=f"期末考試{i}", all_day=True,
                         start_date="2026-12-18", end_date="2026-12-24") for i in range(2)]
    with pytest.raises(CalendarDerivationError, match="命中 2 筆"):
        pick_event(two, "115-1", (r"期末考試", None))


def test_instruction_tie_break_prefers_the_formal_one(events):
    """措辭逐年不同：115-1「開學暨註冊截止日、開學典禮」、115-2「開學正式上課、註冊截止日」。"""
    assert derive_term(events, "115-1").instruction_start == "2026-09-07"
    assert derive_term(events, "115-2").instruction_start == "2027-02-22"


def test_division_specific_variant_loses_to_school_wide(events):
    """111-2 實測有兩筆期末考試：校級的與「進修部期末考試(6/17 補行上班，停課一次)」。
    calendar.json 描述的是全校學期行事曆，學制專屬的是例外附註。"""
    assert derive_term(events, "111-2").final_exam.start == "2023-06-15"


# ----------------------------------------------------------------- 不變量 ①~⑦

def _good_term():
    weeks = derive_weeks(D("2026-09-07"), D("2027-01-11"))
    return AcademicTerm(
        instruction_start="2026-09-07", weeks=weeks,
        midterm=DateRange(start="2026-11-02", end="2026-11-06"),
        final_exam=DateRange(start="2026-12-18", end="2026-12-24"),
        break_start="2027-01-11")


def test_good_term_passes_all_invariants():
    assert check_invariants("115-1", _good_term()) == []


def test_invariant_1_week_count():
    t = _good_term()
    t.weeks = t.weeks[:17]
    assert any(v.startswith("①") for v in check_invariants("115-1", t))


def test_invariant_2_week_continuity():
    t = _good_term()
    t.weeks[5] = TermWeek(number=6, start="2026-10-11", end="2026-10-16")  # 少一天
    assert any(v.startswith("②") for v in check_invariants("115-1", t))


def test_invariant_3_weeks_start_on_sunday():
    """開學日 + 7×(N-1) 那個經典錯誤：校方週次週日起算、開學日是隔天週一。"""
    t = _good_term()
    t.weeks = [TermWeek(number=i + 1,
                        start=(D("2026-09-07") + dt.timedelta(days=7 * i)).isoformat(),
                        end=(D("2026-09-13") + dt.timedelta(days=7 * i)).isoformat())
               for i in range(18)]
    assert any(v.startswith("③") for v in check_invariants("115-1", t))


def test_invariant_4_instruction_inside_week_one():
    t = _good_term()
    t.instruction_start = "2026-10-05"
    assert any(v.startswith("④") for v in check_invariants("115-1", t))


def test_invariant_5_final_exam_inside_term():
    t = _good_term()
    t.final_exam = DateRange(start="2027-02-01", end="2027-02-05")
    assert any(v.startswith("⑤") for v in check_invariants("115-1", t))


def test_invariant_6_break_after_last_week():
    t = _good_term()
    t.break_start = "2026-12-01"
    assert any(v.startswith("⑥") for v in check_invariants("115-1", t))


def test_invariant_7_terms_do_not_overlap():
    a, b = _good_term(), _good_term()          # 兩個同樣的學期 → 必然重疊
    assert any(v.startswith("⑦") for v in check_invariants("115-1", a, ("115-2", b)))


def test_invariant_9_required_fields_enforced_by_model():
    """⑨ 必填非 null 由 pydantic 結構保證——App 要靠這四欄取代中文關鍵字耦合。"""
    with pytest.raises(Exception):
        AcademicTerm(instruction_start="2026-09-07")   # 缺 midterm/final_exam/break_start


# ----------------------------------------------------------------- 不變量⑩ 回歸

def test_reference_covers_ten_terms():
    ref = load_week_table_reference()
    assert len(ref) == 10
    assert all(v["week_count"] == 18 for v in ref.values())


def test_week_table_regression_passes_on_real_feed(events):
    """111~115 十個學期的推導結果必須與校方公告 PDF 的週次表逐筆相同。
    這條在**發佈時**跑（見 build_all_term_calendars），不是只在 pytest 跑。"""
    assert verify_week_table_regression(events) == []


def test_week_table_regression_catches_a_broken_rule(events, monkeypatch):
    """把「第 1 週 = 開學日所在週」改成「開學日當天起算」——這正是校方週日起算 vs
    開學日週一的經典錯誤。回歸必須抓到，而且不只抓到一個學期。"""
    import ntut_catalog.term_calendar as tc
    monkeypatch.setattr(tc, "sunday_on_or_before", lambda d: d)
    bad = tc.verify_week_table_regression(events)
    assert len(bad) == 10
    assert all(v.startswith("⑩") for v in bad)


# ----------------------------------------------------------------- 產出範圍與整體

@pytest.mark.parametrize("today,ay", [
    ("2026-09-16", 115), ("2027-01-15", 115), ("2027-07-31", 115), ("2027-08-01", 116),
])
def test_current_academic_year(today, ay):
    assert current_academic_year(D(today)) == ay


def test_default_terms_covers_current_year_only():
    assert default_terms(D("2026-09-16")) == ["115-1", "115-2"]


def test_invariant_failure_is_still_all_or_nothing(events):
    """**有事件但湊不出合法週次表** → 規則或來源壞了，把另一個學期照發只是把錯誤藏起來。
    108-2（COVID 那年）延長學期，期末考落在推導範圍外、不變量⑤ 擋下。"""
    with pytest.raises(CalendarDerivationError, match="不變量未通過"):
        build_all_term_calendars(events, ["115-1", "108-2"], "u", "sha")


def test_term_not_in_the_feed_yet_is_skipped_not_an_error(events):
    """新學年度的行事曆分批匯入（112 學年度下學期拖到 2024-02），所以每年 8 月之後
    有一段時間 default_terms() 要的學期在 ics 裡是空的。那是常態——安靜跳過，
    不能讓整個 crawl-calendar 非零退出、連事件 feed 一起停更。"""
    got = build_all_term_calendars(events, ["115-1", "105-1"], "u", "sha")
    assert sorted(got) == ["115-1"]


def test_all_terms_missing_returns_empty_without_raising(events):
    """2027-08-01 的實際情境：舊學年度已結束、新學年度還沒匯入，兩個都是空的。
    回空字典、保留既有週次表不動——由 calendar_coverage_check 負責盯，
    不是靠讓管線死掉來通知。"""
    assert build_all_term_calendars(events, ["116-1", "116-2"], "u", "sha") == {}


def test_old_terms_are_not_guaranteed_derivable(events):
    """為什麼「只產當前學年度、舊學期不回填」：108-2（COVID 那年）延長學期，
    期末考 2020-06-29~07-05 落在推導出的學期範圍外，不變量⑤ 擋下。
    回填舊學年度只是多冒險，而 App 只用得到當前學期與下學期。"""
    violations = check_invariants("108-2", derive_term(events, "108-2"))
    assert any(v.startswith("⑤") for v in violations)


def test_build_all_produces_single_key_terms_map(events):
    """逐學期一檔，裡面仍保留單鍵 terms map——讓 App 現行 decoder 一行都不用改。"""
    cals = build_all_term_calendars(events, ["115-1", "115-2"], "u", "sha")
    assert set(cals) == {"115-1", "115-2"}
    for key, cal in cals.items():
        assert list(cal.terms) == [key]
        assert cal.schema_version == 1
        assert cal.week_starts_on == "sunday"
        assert cal.range_end_semantics == "inclusive"
        assert cal.source.derived_fields == ["weeks", "preparation", "enrollment_windows"]


def test_flexible_learning_is_optional_before_115(events):
    """彈性學習週 115 學年度才出現，舊學期 ics 裡沒有這個事件。"""
    assert derive_term(events, "114-1").flexible_learning is None
    assert derive_term(events, "115-1").flexible_learning is not None


def test_matches_human_verified_115_snapshot(events):
    """對人工核對過的 115 學年度快照逐欄相同。midterm 是我方新增（快照漏收、ics 有）。"""
    snapshot = json.loads(SNAPSHOT_115.read_text(encoding="utf-8"))["terms"]
    for term_key in ("115-1", "115-2"):
        got = derive_term(events, term_key).model_dump()
        expected = snapshot[term_key]
        for field, want in expected.items():
            if field == "weeks":
                got_weeks = [{k: w[k] for k in ("number", "start", "end")} for w in got["weeks"]]
                want = [{k: w[k] for k in ("number", "start", "end")} for w in want]
                assert got_weeks == want, f"{term_key}.weeks"
            else:
                assert got[field] == want, f"{term_key}.{field}"
        assert got["midterm"] is not None      # 快照沒有的欄位，ics 有


# ----------------------------------------------------------------- 產物與發佈接線

def _write_one(tmp_path, events, term_key="115-1"):
    from ntut_catalog.artifacts import write_term_calendar
    cal = build_all_term_calendars(events, [term_key], "https://x/basic.ics", "sha")[term_key]
    write_term_calendar(cal, term_key, tmp_path)
    return cal


def test_canonical_then_v1_round_trip(tmp_path, events):
    from models import TermCalendarFile
    from ntut_catalog.artifacts import build_term_calendars_v1
    cal = _write_one(tmp_path, events)
    assert build_term_calendars_v1(tmp_path, "2026-09-16T04:00:00+08:00") == ["115-1"]
    out = TermCalendarFile.model_validate_json(
        (tmp_path / "v1" / "terms" / "115-1" / "calendar.json").read_text(encoding="utf-8"))
    assert out.generated_at is None        # 同 events.json：時間戳用 source.parsed_at
    assert out.terms["115-1"].model_dump() == cal.terms["115-1"].model_dump()


def test_v1_calendar_does_not_require_a_crawled_catalog(tmp_path, events):
    """下學期的週次表往往早於課程目錄就能產（#168 要的正是提前拿到）。
    週次表刻意不綁在「canonical/{term}/catalog.ndjson 存在」這個條件上。"""
    from ntut_catalog.artifacts import build_term_calendars_v1
    _write_one(tmp_path, events, "115-2")
    assert not (tmp_path / "canonical" / "115-2" / "catalog.ndjson").exists()
    assert build_term_calendars_v1(tmp_path, "g") == ["115-2"]
    assert (tmp_path / "v1" / "terms" / "115-2" / "calendar.json").exists()


def test_manifest_carries_calendar_entry(tmp_path, events, sample_result):
    from ntut_catalog.artifacts import build_v1, write_canonical
    write_canonical(sample_result, tmp_path)
    _write_one(tmp_path, events)
    manifest = build_v1(tmp_path, "2026-09-16T04:00:00+08:00")
    entry = manifest.terms["115-1"].calendar
    assert entry is not None
    assert entry.url == "terms/115-1/calendar.json"
    assert entry.sha256 and entry.size > 0


def test_publish_uploads_calendar_with_a_longer_cache(tmp_path, events):
    """一學期最多修訂一兩次 → 長快取；但**不可宣稱 immutable**，開學前會有修正版。"""
    from infra import publish
    from ntut_catalog.artifacts import build_term_calendars_v1
    _write_one(tmp_path, events)
    build_term_calendars_v1(tmp_path, "g")
    files = publish.local_files(tmp_path)
    assert "v1/terms/115-1/calendar.json" in files
    assert publish.cache_control_for("v1/terms/115-1/calendar.json") == \
        "public, max-age=86400, stale-while-revalidate=604800"
    assert publish.r2_key("v1/terms/115-1/calendar.json") == "course/v1/terms/115-1/calendar.json"


def test_pipeline_calendar_also_writes_term_calendars(tmp_path):
    from ntut_catalog import cli, pipeline
    from tests.test_calendar_events import _calendar_ctx
    ctx = _calendar_ctx(tmp_path, SNAPSHOT_ICS.read_text(encoding="utf-8"))
    assert pipeline.run("daily", ["calendar"], [], tmp_path, tmp_path / "stage", ctx=ctx).ok
    assert cli.main(["derive", "--out", str(tmp_path)]) == 0
    for term_key in ("115-1", "115-2"):
        assert (tmp_path / "canonical" / term_key / "calendar.json").exists()
        assert (tmp_path / "v1" / "terms" / term_key / "calendar.json").exists()
    assert (tmp_path / "v1" / "calendar" / "events.json").exists()


def test_term_calendar_bytes_are_stable_across_builds(tmp_path, events):
    """同 events.json：週次表一學期最多改一兩次，沒改的日子不該換 ETag。"""
    from ntut_catalog.artifacts import build_term_calendars_v1
    _write_one(tmp_path, events)
    out = tmp_path / "v1" / "terms" / "115-1" / "calendar.json"
    build_term_calendars_v1(tmp_path, "2026-09-16T04:00:00+08:00")
    first = out.read_bytes()
    build_term_calendars_v1(tmp_path, "2026-09-17T04:00:00+08:00")
    assert out.read_bytes() == first


def test_manifest_calendar_entry_uses_the_independent_schema_version(tmp_path, events, sample_result):
    """manifest 說的版本必須與檔案自己宣告的一致。calendar.json 寫 schema_version=1
    （獨立於全域的 2），manifest entry 若沿用全域值，App 對版本不符是整份拒收——
    而且是靜默失效。"""
    from models import CALENDAR_SCHEMA_VERSION, SCHEMA_VERSION, TermCalendarFile
    from ntut_catalog.artifacts import build_v1, write_canonical
    write_canonical(sample_result, tmp_path)
    _write_one(tmp_path, events)
    manifest = build_v1(tmp_path, "2026-09-19T04:00:00+08:00")
    term = manifest.terms["115-1"]
    published = TermCalendarFile.model_validate_json(
        (tmp_path / "v1" / "terms" / "115-1" / "calendar.json").read_text(encoding="utf-8"))
    assert term.calendar.schema_version == CALENDAR_SCHEMA_VERSION == published.schema_version
    assert term.catalog.schema_version == SCHEMA_VERSION      # 其餘仍走全域版本


# ----------------------------------------------------------------- manifest.calendars

def _publish_calendar(tmp_path, term_key, first_week, weeks=18):
    """直接寫一份 v1 週次表，不經推導——這裡測的是 manifest 的列法，不是推導。"""
    import json
    d = tmp_path / "v1" / "terms" / term_key
    d.mkdir(parents=True, exist_ok=True)
    start = D(first_week)
    (d / "calendar.json").write_text(json.dumps({
        "schema_version": 1, "timezone": "Asia/Taipei", "week_starts_on": "sunday",
        "range_end_semantics": "inclusive",
        "source": {"type": "google_calendar_ics", "url": "u", "content_sha256": "s",
                   "parsed_at": "p", "parser_version": "calendar/1.0.0"},
        "terms": {term_key: {
            "instruction_start": first_week, "break_start": "2027-01-11",
            "midterm": {"start": "2026-11-02", "end": "2026-11-06"},
            "final_exam": {"start": "2026-12-18", "end": "2026-12-24"},
            "weeks": [{"number": i + 1,
                       "start": (start + dt.timedelta(days=7 * i)).isoformat(),
                       "end": (start + dt.timedelta(days=7 * i + 6)).isoformat()}
                      for i in range(weeks)]}}}), encoding="utf-8")


def test_calendars_list_carries_the_coverage_range(tmp_path):
    """App 只讀 manifest 就能挑出該抓哪一份——不必把 8/1 界線複製進需要送審的那一側。"""
    from ntut_catalog.artifacts import _calendar_entries
    _publish_calendar(tmp_path, "115-1", "2026-09-06")
    got = _calendar_entries(tmp_path)
    entry = got["115-1"]
    assert entry.url == "terms/115-1/calendar.json"
    assert (entry.first_week_start, entry.last_week_end) == ("2026-09-06", "2027-01-09")
    assert entry.schema_version == 1        # 獨立版本，與檔案自己宣告的一致


def test_calendars_list_keeps_latest_and_previous_academic_year(tmp_path):
    """範圍＝canonical 裡有週次表的學期之中「最新學年度＋前一學年度」。"""
    from ntut_catalog.artifacts import _calendar_entries
    for term, first in [("113-1", "2024-09-08"), ("114-1", "2025-09-07"),
                        ("115-1", "2026-09-06"), ("115-2", "2027-02-21")]:
        _publish_calendar(tmp_path, term, first)
    got = _calendar_entries(tmp_path)                            # 最新學年度 115
    assert sorted(got) == ["114-1", "115-1", "115-2"]            # 113 被排除
    assert "113-1" in [p.parent.name for p in
                       (tmp_path / "v1" / "terms").glob("*/calendar.json")]  # 檔案仍在


def test_previous_year_fills_the_august_hole(tmp_path):
    """每年 8 月新學年度的 ics 還沒匯入：清單仍列最新已有的那一學年度，不會變空。"""
    from freezegun import freeze_time
    from ntut_catalog.artifacts import _calendar_entries
    _publish_calendar(tmp_path, "115-1", "2026-09-06")
    _publish_calendar(tmp_path, "115-2", "2027-02-21")
    with freeze_time("2027-08-15"):                              # 已是學年度 116
        got = _calendar_entries(tmp_path)
    assert sorted(got) == ["115-1", "115-2"]


def test_new_academic_year_moves_the_window_forward(tmp_path):
    """新學年度的週次表一出現，清單就往前移一年——由內容驅動，不需要日期。"""
    from ntut_catalog.artifacts import _calendar_entries
    for term, first in [("114-1", "2025-09-07"), ("115-1", "2026-09-06"),
                        ("116-1", "2027-09-05")]:
        _publish_calendar(tmp_path, term, first)
    assert sorted(_calendar_entries(tmp_path)) == ["115-1", "116-1"]


def test_calendars_list_does_not_depend_on_system_date(tmp_path):
    """derive 確定性：同一份內容在 7/31 與 8/1（學年度交界）建出同一份清單。"""
    from freezegun import freeze_time
    from ntut_catalog.artifacts import _calendar_entries
    for term, first in [("113-1", "2024-09-08"), ("114-1", "2025-09-07"),
                        ("115-1", "2026-09-06")]:
        _publish_calendar(tmp_path, term, first)
    results = []
    for day in ("2026-07-31", "2026-08-01", "2030-01-01"):
        with freeze_time(day):
            results.append(sorted(_calendar_entries(tmp_path)))
    assert results[0] == results[1] == results[2] == ["114-1", "115-1"]


def test_calendars_list_is_bounded(tmp_path):
    """每年 +2 但清單封頂 4 筆——清單是發現機制，不是歷史檔案館。"""
    from ntut_catalog.artifacts import _calendar_entries
    for ay in range(110, 121):
        for sem in (1, 2):
            _publish_calendar(tmp_path, f"{ay}-{sem}", "2026-09-06")
    assert sorted(_calendar_entries(tmp_path)) == ["119-1", "119-2", "120-1", "120-2"]


def test_manifest_lists_a_calendar_even_without_a_catalog(tmp_path, events, sample_result):
    """115-2 沒有課程目錄、進不了 manifest.terms（catalog 必填），
    但必須出現在 calendars 裡，否則 App 無從發現它——實測 404 的根因。"""
    from ntut_catalog.artifacts import build_v1, write_canonical
    write_canonical(sample_result, tmp_path)
    _write_one(tmp_path, events, "115-1")
    _write_one(tmp_path, events, "115-2")
    manifest = build_v1(tmp_path, "2026-09-19T04:00:00+08:00")
    assert "115-2" not in manifest.terms          # 沒有 catalog
    assert sorted(manifest.calendars) == ["115-1", "115-2"]


def test_term_calendar_is_not_rewritten_when_content_is_unchanged(tmp_path, events):
    """`source.parsed_at` 每次跑都不同，但那不是內容的一部分。不比對就每天重寫 →
    ETag 每天失效 → max-age=86400 的長快取白設。這是 #89 漏掉的另一半。"""
    import time
    from ntut_catalog.artifacts import write_term_calendar
    first = build_all_term_calendars(events, ["115-1"], "u", "sha")["115-1"]
    assert write_term_calendar(first, "115-1", tmp_path) is True
    time.sleep(1.1)                       # parsed_at 用秒精度
    second = build_all_term_calendars(events, ["115-1"], "u", "sha")["115-1"]
    assert second.source.parsed_at != first.source.parsed_at
    assert write_term_calendar(second, "115-1", tmp_path) is False


def test_term_calendar_is_rewritten_when_content_really_changed(tmp_path, events):
    from ntut_catalog.artifacts import write_term_calendar
    cal = build_all_term_calendars(events, ["115-1"], "u", "sha")["115-1"]
    write_term_calendar(cal, "115-1", tmp_path)
    changed = cal.model_copy(deep=True)
    changed.terms["115-1"].break_start = "2027-01-12"      # 學校改了寒假起日
    assert write_term_calendar(changed, "115-1", tmp_path) is True


def test_published_calendar_bytes_survive_a_rerun(tmp_path, events):
    """端到端：同樣的來源連跑兩次，v1 產物必須 byte-identical。"""
    import time
    from ntut_catalog.artifacts import build_term_calendars_v1, write_term_calendar
    out = tmp_path / "v1" / "terms" / "115-1" / "calendar.json"
    write_term_calendar(build_all_term_calendars(events, ["115-1"], "u", "sha")["115-1"],
                        "115-1", tmp_path)
    build_term_calendars_v1(tmp_path, "2026-09-20T05:00:00+08:00")
    first = out.read_bytes()
    time.sleep(1.1)
    write_term_calendar(build_all_term_calendars(events, ["115-1"], "u", "sha")["115-1"],
                        "115-1", tmp_path)
    build_term_calendars_v1(tmp_path, "2026-09-21T05:00:00+08:00")
    assert out.read_bytes() == first


# ----------------------------------------------------------------- 選課相關窗口（issue #111）

def _windows(events, term_key):
    return [(w.kind, w.target_term, w.division, w.start, w.end)
            for w in derive_term(events, term_key).enrollment_windows]


def test_enrollment_windows_115_1(events):
    """115-1 的檔：新生預選、開學後加退選日夜拆兩筆；期中撤選「開始」10/05 與日夜「結束」11/20、
    11/21 配對；12/07 的「115學年度第2學期網路選課」發生在 115-1 → 在這裡，target 115-2。"""
    assert _windows(events, "115-1") == [
        ("freshman_preselection", "115-1", "day", "2026-08-19T00:00:00+08:00",
         "2026-09-01T17:00:00+08:00"),
        ("freshman_preselection", "115-1", "evening", "2026-08-19T00:00:00+08:00",
         "2026-09-01T21:00:00+08:00"),
        ("post_start_add_drop", "115-1", "day", "2026-09-07T00:00:00+08:00",
         "2026-09-18T17:00:00+08:00"),
        ("post_start_add_drop", "115-1", "evening", "2026-09-07T00:00:00+08:00",
         "2026-09-19T21:00:00+08:00"),
        ("midterm_withdrawal", "115-1", "day", "2026-10-05T00:00:00+08:00",
         "2026-11-20T17:00:00+08:00"),
        # 進修部撤選也是 17:00 截止（事件本身寫 17:00）
        ("midterm_withdrawal", "115-1", "evening", "2026-10-05T00:00:00+08:00",
         "2026-11-21T17:00:00+08:00"),
        ("preselection", "115-2", "day", "2026-12-07T00:00:00+08:00", "2026-12-18T17:00:00+08:00"),
        ("preselection", "115-2", "evening", "2026-12-07T00:00:00+08:00",
         "2026-12-19T21:00:00+08:00"),
    ]


def test_enrollment_windows_115_2_hosts_116_1_preselection(events):
    """116-1 預選（2027-05-24）發生在 115-2 → 放在 115-2 的檔、target 116-1。
    改版前它歸 116-1，而 116-1 的週次表要到 2027-08 才推得出來 → 整個窗口被默默丟掉。"""
    got = _windows(events, "115-2")
    assert ("post_start_add_drop", "115-2", "evening", "2027-02-22T00:00:00+08:00",
            "2027-03-05T21:00:00+08:00") in got
    assert ("midterm_withdrawal", "115-2", "day", "2027-03-22T00:00:00+08:00",
            "2027-05-07T17:00:00+08:00") in got
    assert got[-2:] == [
        ("preselection", "116-1", "day", "2027-05-24T00:00:00+08:00", "2027-06-04T17:00:00+08:00"),
        ("preselection", "116-1", "evening", "2027-05-24T00:00:00+08:00",
         "2027-06-05T21:00:00+08:00"),
    ]
    assert not any(k == "preselection" and t == "115-2" for k, t, *_ in got)
    uids = {w.kind: w.source_uids for w in derive_term(events, "115-2").enrollment_windows}
    assert len(uids["midterm_withdrawal"]) == 2          # 開始＋結束兩筆事件


@pytest.mark.parametrize("term_key, expected", [
    # 標題分部別、一筆涵蓋兩部別（「日間部 17:00 截止，進修部 21:00 截止」）→ 拆兩窗口
    ("114-2", {("post_start_add_drop", "day"): "2026-03-09T17:00:00+08:00",
               ("post_start_add_drop", "evening"): "2026-03-09T21:00:00+08:00"}),
    # 111-1：「進修部期中撤選結束(截止)」沒寫時刻 → 撤選的進修部預設也是 17:00
    ("111-1", {("midterm_withdrawal", "evening"): "2022-12-03T17:00:00+08:00",
               ("preselection", "day"): "2023-01-06T17:00:00+08:00"}),
    # 選 111-1 的預選（2022-06，未分部別的單筆）發生在 110-2 → 在 110-2 的檔裡
    ("110-2", {("preselection", "all"): "2022-06-17T17:00:00+08:00"}),
    # 113-2：兩筆一模一樣的「期中撤選結束」去重；未標部別的兩筆 → 早者日間部、晚者進修部
    ("113-2", {("midterm_withdrawal", "day"): "2025-05-09T17:00:00+08:00",
               ("midterm_withdrawal", "evening"): "2025-05-10T17:00:00+08:00",
               ("post_start_add_drop", "all"): "2025-03-03T17:00:00+08:00"}),
    # 112-1：「新生網路預選(日間部 17:00 截止) (進修部 21:00 截止)」
    ("112-1", {("freshman_preselection", "day"): "2023-09-05T17:00:00+08:00",
               ("freshman_preselection", "evening"): "2023-09-05T21:00:00+08:00"}),
])
def test_enrollment_windows_tolerate_title_variants(events, term_key, expected):
    got = {(k, d): e for k, _, d, _, e in _windows(events, term_key)}
    for key, end in expected.items():
        assert got.get(key) == end, (term_key, key)


def test_enrollment_windows_every_term_110_to_115(events):
    """110～115 學年度每學期：撤選日夜兩窗口、開學後加退選、（選下學期的）預選都推得出來，且全過不變量。"""
    for y in range(110, 116):
        for sem in (1, 2):
            key = f"{y}-{sem}"
            term = derive_term(events, key)
            kinds = {w.kind for w in term.enrollment_windows}
            assert {"preselection", "post_start_add_drop", "midterm_withdrawal"} <= kinds, key
            nxt = f"{y}-2" if sem == 1 else f"{y + 1}-1"
            assert {w.target_term for w in term.enrollment_windows
                    if w.kind == "preselection"} == {nxt}, key
            assert all(w.target_term == key for w in term.enrollment_windows
                       if w.kind != "preselection"), key
            assert ("freshman_preselection" in kinds) == (sem == 1), key
            divs = [w.division for w in term.enrollment_windows if w.kind == "midterm_withdrawal"]
            assert divs == ["day", "evening"], key
            assert check_window_invariants(key, term) == [], key


def _ev(uid, summary, start, end=None, all_day=True):
    from models import CalendarEvent
    if all_day:
        return CalendarEvent(uid=uid, summary=summary, all_day=True, start_date=start,
                             end_date=end or start)
    return CalendarEvent(uid=uid, summary=summary, all_day=False, start_at=start, end_at=end)


def test_selection_target_term():
    from ntut_catalog.term_calendar import selection_target_term
    assert selection_target_term(_ev("a", "115學年度第2學期網路選課(日間部/全校)",
                                     "2026-12-07")) == "115-2"
    assert selection_target_term(_ev("b", "110 學年度第 2 學期網路選課", "2022-01-03")) == "110-2"
    assert selection_target_term(_ev("c", "108學年度第一學期網路選課", "2019-06-03")) == "108-1"
    assert selection_target_term(_ev("d", "108-2網路選課", "2019-12-23")) == "108-2"
    # 沒寫學期 → 舉行日所在學期的下一學期
    assert selection_target_term(_ev("e", "第二學期網路選課", "2020-12-28")) == "109-2"
    assert selection_target_term(_ev("f", "網路選課", "2021-06-07")) == "110-1"


def test_timed_event_ending_at_midnight_means_previous_day():
    """有時刻、結束在 00:00 的事件（ics end-exclusive 寫法）→ 截止日是前一天，時刻用預設。"""
    from ntut_catalog.term_calendar import _close_at
    ev = _ev("x", "108-2網路選課", "2019-12-23T00:00:00+08:00", "2020-01-04T00:00:00+08:00",
             all_day=False)
    assert _close_at(ev, "all", False).isoformat() == "2020-01-03T17:00:00+08:00"


def test_underivable_windows_are_dropped_with_warning_not_raised(events, caplog):
    """撤選只有「結束」沒有「開始」→ 該窗口不產出、warning，週次表照常。"""
    broken = [e for e in events if not (e.summary.startswith("期中撤選開始")
                                        and e.start_date == "2026-10-05")]
    with caplog.at_level("WARNING"):
        term = derive_term(broken, "115-1")
    assert term.weeks and len(term.weeks) == 18
    assert "midterm_withdrawal" not in {w.kind for w in term.enrollment_windows}
    assert "post_start_add_drop" in {w.kind for w in term.enrollment_windows}
    assert "無法配對" in caplog.text


def test_window_invariants_reject_out_of_range(events):
    from models import EnrollmentWindow
    from ntut_catalog.term_calendar import window_violations
    term = derive_term(events, "115-1")
    bad = EnrollmentWindow(kind="midterm_withdrawal", target_term="115-1", division="day",
                           start="2027-02-01T00:00:00+08:00", end="2027-01-01T00:00:00+08:00")
    got = window_violations("115-1", term, bad)
    assert any("不晚於開始" in v for v in got) and any("上課期間" in v for v in got)
    late = EnrollmentWindow(kind="freshman_preselection", target_term="115-1", division="day",
                            start="2026-09-01T00:00:00+08:00", end="2026-09-10T17:00:00+08:00")
    assert any("晚於開學日" in v for v in window_violations("115-1", term, late))
    wrong = EnrollmentWindow(kind="preselection", target_term="116-1", division="day",
                             start="2026-12-07T00:00:00+08:00", end="2026-12-18T17:00:00+08:00")
    assert any("不是 115-1 的下一學期" in v for v in window_violations("115-1", term, wrong))
    early = EnrollmentWindow(kind="preselection", target_term="115-2", division="day",
                             start="2026-06-08T00:00:00+08:00", end="2026-06-19T17:00:00+08:00")
    assert any("早於所在學期開學日" in v for v in window_violations("115-1", term, early))
    mism = EnrollmentWindow(kind="midterm_withdrawal", target_term="115-2", division="day",
                            start="2026-10-05T00:00:00+08:00", end="2026-11-20T17:00:00+08:00")
    assert any("應等於所在學期" in v for v in window_violations("115-1", term, mism))
    far = EnrollmentWindow(kind="post_start_add_drop", target_term="115-1", division="day",
                           start="2026-10-01T00:00:00+08:00", end="2026-10-10T17:00:00+08:00")
    assert any("距開學日" in v for v in window_violations("115-1", term, far))


def test_calendar_json_unchanged_windows_not_rewritten(tmp_path, events):
    """加了 enrollment_windows 之後，「內容沒變就不重寫」照舊成立（parsed_at 不算內容）。"""
    from ntut_catalog.artifacts import write_term_calendar
    cal = build_all_term_calendars(events, ["115-1"], "u", "sha")["115-1"]
    assert write_term_calendar(cal, "115-1", tmp_path) is True
    again = build_all_term_calendars(events, ["115-1"], "u", "sha")["115-1"]
    again.source.parsed_at = "2099-01-01T00:00:00+08:00"
    assert write_term_calendar(again, "115-1", tmp_path) is False
    changed = again.model_copy(deep=True)
    changed.terms["115-1"].enrollment_windows = changed.terms["115-1"].enrollment_windows[:-1]
    assert write_term_calendar(changed, "115-1", tmp_path) is True
