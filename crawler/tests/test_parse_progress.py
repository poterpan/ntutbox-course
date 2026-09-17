"""逐週進度 parser（契約二）：POC 保真、6 條陷阱、三條新規則的接受與拒絕、回歸門檻。

**拒絕案例與接受案例同等重要**——誤把章節當週次是使用者看得見的錯誤，比空白嚴重得多。
"""
import datetime as dt
import gzip
import json
from pathlib import Path

import pytest

from models import TermWeek
from ntut_catalog.parse_progress import (
    DEFAULT_WEEK_COUNT,
    WeekSegment,
    build_weekly_progress,
    order_candidates,
    parse_anchored_numbered_list,
    parse_date_list,
    parse_numbered_date_table,
    parse_schedule,
    resolve_week,
)

FIX = Path(__file__).parent / "fixtures" / "weekly_progress"
GOLD = json.loads((FIX / "gold_cases.json").read_text(encoding="utf-8"))
OBSERVED = json.loads((FIX / "observed_115-1_range_cases.json").read_text(encoding="utf-8"))
POC_REPORT = json.loads((FIX / "115-1-poc-report.json").read_text(encoding="utf-8"))
CORPUS = FIX / "schedules-115-1-c3cd485c.json.gz"


ICS = (Path(__file__).resolve().parents[2] / "docs" / "research" / "assets"
       / "2026-09-16-calendar-ics-evaluation" / "raw" / "gcal-basic.ics")


@pytest.fixture(scope="module")
def term():
    """115-1 的真實行事曆（契約三推導）。日期／錨點規則要吃它：
    `weeks[]` 用來映射日期，`midterm` 用來當純編號清單的錨點。"""
    from ntut_catalog.calendar_events import parse_calendar_events
    from ntut_catalog.term_calendar import derive_term
    feed = parse_calendar_events(ICS.read_text(encoding="utf-8"), today=dt.date(2026, 9, 16))
    return derive_term(feed.events, "115-1")


@pytest.fixture(scope="module")
def term_weeks(term):
    return term.weeks


@pytest.fixture(scope="module")
def corpus():
    with gzip.open(CORPUS, "rt", encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------- POC 保真

@pytest.mark.parametrize("case", GOLD, ids=[c["name"] for c in GOLD])
def test_gold_cases_reproduce_poc(case):
    result = parse_schedule(case["text"])
    assert [[s.start_week, s.end_week, s.topic] for s in result.segments] == \
        [list(x) for x in case["segments"]]
    for week, want in case.get("states", {}).items():
        assert resolve_week(result, int(week))["status"] == want, f"week {week}"


@pytest.mark.parametrize("case", OBSERVED["cases"], ids=[c["offering_id"] for c in OBSERVED["cases"]])
def test_observed_115_1_samples_reproduce_poc(case):
    """7 個真實 range-heavy 樣本，涵蓋完整 range 表、備註陷阱、list marker、
    校方異常標點（`第13-15: 週`）。**逐段逐字通過**。"""
    result = parse_schedule(case["schedule"])
    assert [[s.start_week, s.end_week, s.topic] for s in result.segments] == \
        [list(x) for x in case["segments"]]


# ----------------------------------------------------------------- 6 條陷阱

def test_trap1_week19_is_not_week9():
    """`第19週` 若 regex 沒有數字邊界，會被錯讀成第 9 週。"""
    assert [s.start_week for s in parse_schedule("第19週 期末").segments] == []


def test_trap2_note_after_week_is_not_a_topic():
    """`第4週後的進度需自行規劃` 是備註，不是第 4 週的 topic。"""
    assert parse_schedule("第4週後的進度需由各組自行規劃").segments == []


def test_trap3_chinese_duration_without_prefix_is_rejected():
    """`一週／二週` = 這單元要花一到兩週，不是第 1／2 週。中文數字沒有「第」就保守拒絕。"""
    assert parse_schedule("導論 一週").segments == []
    assert [s.start_week for s in parse_schedule("第一週 導論").segments] == [1]
    # 阿拉伯數字形式仍接受——那是來源主流的表格格式
    assert [s.start_week for s in parse_schedule("1-4週 導論").segments] == [1]


def test_trap4_only_first_marker_per_line():
    """`Week 2: class time may move to week 3 …` 後半的 week 是敘述，不是新的一列。"""
    segs = parse_schedule("Week 2: class time may move to week 3 for the holiday").segments
    assert [s.start_week for s in segs] == [2]


def test_trap5_bilingual_stays_ambiguous_without_pairing():
    """中英各寫一遍會產生同週不同語言的候選；沒有可靠語言配對時不得硬合併字串。"""
    result = parse_schedule("第3週 機構之運動\nWeek 3: Kinematics of Mechanisms")
    assert resolve_week(result, 3)["status"] == "ambiguous"


def test_trap6_range_with_week_char_on_both_ends():
    """`第4週～第8週` 兩端都有「週」，range regex 必須整段吃掉，否則會拆成兩個單週。"""
    segs = parse_schedule("第4週～第8週 專題").segments
    assert [(s.start_week, s.end_week) for s in segs] == [(4, 8)]


# ----------------------------------------------------------------- 規則 (a) 雙語配對

def _seg(topic):
    return WeekSegment(3, 3, topic, "line", 1, "第3週", "single")


def test_rule_a_stacks_all_candidates_cjk_first():
    """同一週多個候選 → 全部疊加，CJK 佔比高的排前面（App 取 topics[0] 就是中文）。"""
    ordered = order_candidates([_seg("Kinematics of Mechanisms"), _seg("機構之運動")])
    assert [s.topic for s in ordered] == ["機構之運動", "Kinematics of Mechanisms"]


def test_rule_a_order_is_independent_of_input_order():
    a = order_candidates([_seg("機構之運動"), _seg("Kinematics")])
    b = order_candidates([_seg("Kinematics"), _seg("機構之運動")])
    assert [s.topic for s in a] == [s.topic for s in b]


def test_rule_a_keeps_same_language_candidates_too():
    """2026-09-17 改：原本同語系會被整週丟棄，現在照收。
    實測 361535 第 12 週教師真的寫了兩次（第11/12週、第12/13週），丟掉等於漏一週。"""
    assert len(order_candidates([_seg("主題A"), _seg("主題B"), _seg("Topic C")])) == 3


def test_rule_a_drops_empty_topics():
    assert [s.topic for s in order_candidates([_seg("機構之運動"), _seg("")])] == ["機構之運動"]


def test_ambiguity_no_longer_downgrades_status(term):
    """沒有東西被丟掉了，partial 只應代表「有週次沒資料」。"""
    text = "\n".join(f"第{i}週 主題{i}\nWeek {i}: Topic {i}" for i in range(1, 19))
    wp = build_weekly_progress(text, 18, term)
    assert wp.status == "resolved"
    assert wp.weeks[2].topics == ["主題3", "Topic 3"]
    assert wp.notes == []


def test_many_candidates_are_noted_but_kept(term):
    """超過 3 個候選時記一行 notes，讓 App 自己決定要不要截——但不丟。"""
    text = "第5週 A\n第5週 B\n第5週 C\n第5週 D\n" + "\n".join(f"第{i}週 主題{i}" for i in range(1, 19) if i != 5)
    wp = build_weekly_progress(text, 18, term)
    assert len(wp.weeks[4].topics) == 4
    assert any("4 個候選" in n for n in wp.notes)

# ----------------------------------------------------------------- 規則 (b) 編號＋日期表

def _table(rows=18, start=dt.date(2026, 9, 8), step=7, gap_at=None):
    lines = []
    day = start
    for i in range(1, rows + 1):
        lines.append(f"{i}\t{day.month}/{day.day}\t主題{i}")
        day += dt.timedelta(days=step * 2 if gap_at == i else step)
    return "\n".join(lines)


def test_rule_b_accepts_self_verifying_table():
    """首欄 1..18 與「每列差 7 天」互相證明——資料自己驗證自己，所以自動接受。"""
    rows = parse_numbered_date_table(_table(), 2026)
    assert rows is not None and len(rows) == 18
    assert rows[0][:2] == (1, "2026-09-08")


def test_rule_b_handles_year_rollover():
    """月份回捲（12 → 1）時 +1 年。"""
    rows = parse_numbered_date_table(_table(start=dt.date(2026, 11, 2)), 2026)
    assert rows[-1][1].startswith("2027-")


@pytest.mark.parametrize("text,base,why", [
    (_table(gap_at=10), 2026, "有一對間隔 14 天（調課／放假），這時不要猜"),
    (_table(rows=8), 2026, "列數 < 12"),
    ("2\t9/8\t主題\n3\t9/15\t主題", 2026, "序列不從 1 開始"),
    ("\n".join(f"{i}\t主題{i}" for i in range(1, 19)), 2026, "沒有日期欄"),
])
def test_rule_b_rejects(text, base, why):
    assert parse_numbered_date_table(text, base) is None, why


def test_bare_numbered_list_with_a_plausible_row_count_is_now_accepted(term):
    """2026-09-17 政策改變。原規格寫「項數恰等於 week_count 只是巧合」——那是逐筆的直覺，
    看母體就站不住：115-1 全量掃過，連續編號清單的列數在 6~15 列各只有 ≤19 筆，
    16 列跳到 77、18 列跳到 110。章節清單不會剛好在兩個合法授課週數疊出兩根柱子。"""
    assert build_weekly_progress("\n".join(f"{i}. 章節{i}" for i in range(1, 19)),
                                 18, term).status == "resolved"


def test_bare_numbered_list_with_an_implausible_row_count_is_still_rejected(term):
    """14 列落在背景雜訊區間，沒有任何證據支持它是週次——仍然拒絕。"""
    assert build_weekly_progress("\n".join(f"{i}. 章節{i}" for i in range(1, 15)),
                                 18, term).status == "unparsed"


# ----------------------------------------------------------------- 規則 (c) 純日期清單

def _date_list(n=18, extra=""):
    body = "\n".join(
        f"{(dt.date(2026, 9, 8) + dt.timedelta(days=7 * i)).strftime('%m/%d')}  主題{i + 1}"
        for i in range(n))
    return body + extra


def test_rule_c_maps_dates_to_weeks(term_weeks):
    rows = parse_date_list(_date_list(), term_weeks)
    assert rows is not None and len(rows) == 18
    assert rows[0][0] == 1 and rows[-1][0] == 18


@pytest.mark.parametrize("text_suffix,why", [
    ("\n8/1  暑期先修", "日期落在學期外 → 整份拒絕"),
    ("\n09/09  重複那一週", "映射結果有重複週次 → 整份拒絕"),
])
def test_rule_c_rejects_whole_schedule(term_weeks, text_suffix, why):
    """日期表格式通常一致，局部失敗代表判讀方向錯了，**不做部分接受**。"""
    assert parse_date_list(_date_list() + text_suffix, term_weeks) is None, why


def test_rule_c_skips_when_week_markers_present(term_weeks):
    assert parse_date_list("第1週 9/8 主題", term_weeks) is None


def test_rule_c_needs_contract_three(term):
    """需要契約三先就位；沒有行事曆就跳過日期／錨點規則，marker 路徑照常。"""
    assert parse_date_list(_date_list(), []) is None
    assert build_weekly_progress(_date_list(), 18, None).status == "unparsed"
    assert build_weekly_progress(_date_list(), 18, term).status == "resolved"


# ----------------------------------------------------------------- 三態

@pytest.mark.parametrize("text,status", [
    ("", "unparsed"),
    ("   ", "unparsed"),
    ("TBA", "unparsed"),
    ("依課堂狀況調整", "unparsed"),
    ("第1週：課程介紹", "partial"),
    ("\n".join(f"第{i}週 主題{i}" for i in range(1, 19)), "resolved"),
])
def test_three_states(text, status, term):
    assert build_weekly_progress(text, 18, term).status == status


def test_unparsed_is_still_written_out(term):
    """unparsed 也要寫出來（帶 parser_version），App 才能誠實顯示「教師未提供」
    而不是「載入中」。"""
    wp = build_weekly_progress("TBA", 18, term)
    assert wp.parser_version.startswith("progress/")
    assert wp.parsed_at and wp.source_schedule_sha256
    assert wp.weeks == []


def test_original_schedule_is_never_touched(term):
    from models import Syllabus
    from ntut_catalog.parse_progress import attach_weekly_progress
    original = "第1週：課程介紹"
    syl = Syllabus(schedule=original)
    attach_weekly_progress([syl], term)
    assert syl.schedule == original          # 原文一律保留、不覆寫
    assert syl.weekly_progress is not None


def test_sha256_changes_with_source(term):
    a = build_weekly_progress("第1週 A", 18, term).source_schedule_sha256
    b = build_weekly_progress("第1週 B", 18, term).source_schedule_sha256
    assert a != b


def test_ambiguous_week_is_kept_by_stacking(term):
    """2026-09-17 改：原本多候選整週丟棄 + 留 note + 降 partial，現在疊加保留。
    status 仍是 partial，但原因是第 2、4~18 週沒資料，不是第 3 週有歧義。"""
    wp = build_weekly_progress("第1週 導論\n第3週 主題A\n第3週 主題B", 18, term)
    assert [w.week for w in wp.weeks] == [1, 3]
    assert wp.weeks[1].topics == ["主題A", "主題B"]
    assert wp.notes == []


def test_no_candidates_field_is_exposed(term):
    """刻意不設 candidates 欄位——把不確定性丟給 client 只會讓每個 consumer
    各自發明取捨、而且發明得不一致。"""
    wp = build_weekly_progress("第1週 導論", 18, term)
    assert "candidates" not in wp.model_dump()


def test_multi_syllabus_each_gets_its_own(term):
    """115-1 有 112 個開課實例的不同教師寫了互相衝突的進度，挑哪一位是 consumer 的事。
    **不合併、不投票、不取第一份。**"""
    from models import Syllabus
    from ntut_catalog.parse_progress import attach_weekly_progress
    a = Syllabus(teacher_code="A", schedule="第1週 甲老師的主題")
    b = Syllabus(teacher_code="B", schedule="第1週 乙老師的主題")
    attach_weekly_progress([a, b], term)
    assert a.weekly_progress.weeks[0].topics == ["甲老師的主題"]
    assert b.weekly_progress.weeks[0].topics == ["乙老師的主題"]
    assert a.weekly_progress.source_schedule_sha256 != b.weekly_progress.source_schedule_sha256


# ----------------------------------------------------------------- 回歸門檻（CI 必跑）

def test_corpus_matches_the_poc_baseline(corpus):
    """語料本身沒被動過——POC 的 115-1-poc-report.json 就是對這一份跑出來的。"""
    assert corpus["source_commit"] == POC_REPORT["source"]["commit"]
    assert len(corpus["schedules"]) == POC_REPORT["schedules"]


def test_marker_parser_never_regresses_below_poc(corpus):
    """移植保真的下限。

    PR C 時這裡是**逐項相等**；加了規則 (e)（跨行 marker）之後 marker 路徑刻意變強，
    等號不再成立，所以改成「不得低於 POC」。逐字保真的保證改由 gold_cases（19 筆）
    與 observed 樣本（7 筆）承擔——那兩份仍然是逐段逐字相等。
    """
    with_segments = resolved = ambiguous = 0
    for text in corpus["schedules"]:
        result = parse_schedule(text)
        if result.segments:
            with_segments += 1
        for week in range(1, DEFAULT_WEEK_COUNT + 1):
            state = resolve_week(result, week)["status"]
            resolved += state == "resolved"
            ambiguous += state == "ambiguous"
    assert with_segments >= POC_REPORT["schedules_with_segments"]   # POC 1255
    assert resolved >= 18735          # POC: resolved lookup cells；規則 (e) 推到 19063
    # ambiguous 的絕對數已不重要——2026-09-17 起多候選一律疊加、不再丟棄整週。
    # 這裡只確認它沒有爆炸式成長（代表 marker 規則把不相干的東西也收進來了）。
    assert ambiguous <= 1200          # POC 734


def test_regression_thresholds_never_go_down(corpus, term):
    """新規則只能把數字往上推；往下就是回歸。門檻取自 POC 全量跑（§3 表格）。"""
    total = len(corpus["schedules"])
    cells = total * DEFAULT_WEEK_COUNT
    parsed = cells_with_topic = 0
    for text in corpus["schedules"]:
        wp = build_weekly_progress(text, DEFAULT_WEEK_COUNT, term)
        if wp.status != "unparsed":
            parsed += 1
        cells_with_topic += len(wp.weeks)
    coverage = parsed / total
    cell_rate = cells_with_topic / cells
    assert coverage >= 0.5697, f"schedule_parse_coverage 下降到 {coverage:.4f}"
    assert cell_rate >= 0.4725, f"resolved_lookup_cell_rate 下降到 {cell_rate:.4f}"
    # 規則 (a)~(e) 實際把兩個數字推到這裡；掉回門檻附近代表有規則失效了
    # 2026-09-17 一輪：候選疊加、英文 list／序數／WK#／全形／點號、列數與表頭證據
    assert coverage >= 0.776, f"coverage {coverage:.4f} 低於本輪應達到的水準"
    assert cell_rate >= 0.697, f"cell_rate {cell_rate:.4f} 低於本輪應達到的水準"


# ----------------------------------------------------------------- 產物與離線重產

def _detail_with_schedule(term_key="115-1", offering_id="360744", schedule="第1週：課程介紹"):
    from models import CourseDetail, LocalizedText, Syllabus
    return CourseDetail(
        term_key=term_key, offering_id=offering_id, course_code="123456",
        name=LocalizedText(zh="測試課程"),
        syllabi=[Syllabus(teacher_code="23602", teacher_name="測試教師", schedule=schedule)],
        generated_at="2026-09-16T00:00:00+08:00")


def test_weekly_progress_reaches_the_published_course_json(tmp_path, term):
    """發佈端零改動：details.ndjson 的整行 JSON 被原樣炸成 v1/.../course/{id}.json，
    新欄自動流到 CDN。這條釘住那個假設。"""
    from ntut_catalog.artifacts import build_v1
    from ntut_catalog.detail import write_details
    from ntut_catalog.parse_progress import attach_weekly_progress
    detail = _detail_with_schedule()
    attach_weekly_progress(detail.syllabi, term)
    write_details([detail], tmp_path)
    build_v1(tmp_path, "2026-09-16T00:00:00+08:00")
    published = json.loads(
        (tmp_path / "v1" / "terms" / "115-1" / "course" / "360744.json").read_text(encoding="utf-8"))
    wp = published["syllabi"][0]["weekly_progress"]
    assert wp["status"] == "partial"
    assert wp["weeks"][0]["topics"] == ["課程介紹"]
    assert published["syllabi"][0]["schedule"] == "第1週：課程介紹"   # 原文仍在


def test_reprocess_rewrites_canonical_and_writes_a_report(tmp_path):
    """parser_version 升版時不必重爬學校系統就能重產（照 recategorize/rematric 先例）。"""
    from ntut_catalog.detail import write_details
    from ntut_catalog.reprocess import reprocess_progress
    write_details([_detail_with_schedule()], tmp_path)          # 先寫一份沒有 weekly_progress 的
    nd = tmp_path / "canonical" / "115-1" / "details.ndjson"
    assert json.loads(nd.read_text(encoding="utf-8"))["syllabi"][0]["weekly_progress"] is None

    reports = reprocess_progress(tmp_path, ["115-1"], "2026-09-16T04:00:00+08:00")
    assert json.loads(nd.read_text(encoding="utf-8"))["syllabi"][0]["weekly_progress"] is not None
    report = json.loads((tmp_path / "canonical" / "reports" / "115-1" / "weekly-progress.json")
                        .read_text(encoding="utf-8"))
    assert report == reports[0]
    assert report["status_counts"] == {"resolved": 0, "partial": 1, "unparsed": 0}
    assert report["term_weeks_available"] is False              # 這個 tmp 沒有 calendar.json


def test_reprocess_picks_up_the_term_when_calendar_exists(tmp_path, events_feed_terms):
    """有契約三的 calendar.json 時，日期／錨點規則自動啟用。"""
    from ntut_catalog.artifacts import write_term_calendar
    from ntut_catalog.detail import write_details
    from ntut_catalog.reprocess import load_term, reprocess_progress
    write_term_calendar(events_feed_terms["115-1"], "115-1", tmp_path)
    assert load_term(tmp_path, "115-1") is not None
    write_details([_detail_with_schedule(schedule=_date_list())], tmp_path)
    report = reprocess_progress(tmp_path, ["115-1"], "2026-09-16T04:00:00+08:00")[0]
    assert report["term_weeks_available"] is True
    assert report["status_counts"]["resolved"] == 1     # 純日期清單被規則 (c) 救回


@pytest.fixture(scope="module")
def events_feed_terms():
    from ntut_catalog.calendar_events import parse_calendar_events
    from ntut_catalog.term_calendar import build_all_term_calendars
    ics = (Path(__file__).resolve().parents[2] / "docs" / "research" / "assets"
           / "2026-09-16-calendar-ics-evaluation" / "raw" / "gcal-basic.ics")
    feed = parse_calendar_events(ics.read_text(encoding="utf-8"), today=dt.date(2026, 9, 16))
    return build_all_term_calendars(feed.events, ["115-1"], "u", "sha")


# ----------------------------------------------------------------- App 端契約 fixture

@pytest.mark.parametrize("name,expect", [
    ("course-resolved.json", ["resolved"]),
    ("course-partial.json", ["partial"]),
    ("course-unparsed.json", ["unparsed"]),
    ("course-multi-syllabus.json", ["partial", "partial"]),
])
def test_app_contract_fixtures_stay_valid(name, expect):
    """App 端手寫 Swift Codable 對照這些 fixture 做雙邊契約測試。
    形狀一變這裡就會紅，避免發布端悄悄改掉 App 依賴的欄位。"""
    from models import CourseDetail
    detail = CourseDetail.model_validate_json((FIX / name).read_text(encoding="utf-8"))
    assert [s.weekly_progress.status for s in detail.syllabi] == expect
    for syllabus in detail.syllabi:
        wp = syllabus.weekly_progress
        assert wp.parser_version and wp.parsed_at and wp.source_schedule_sha256
        assert syllabus.schedule, "原文 schedule 必須保留"


def test_multi_syllabus_fixture_really_conflicts():
    """兩位教師寫了互相衝突的進度——這正是「不合併、不投票」要 App 自己選的情境。"""
    from models import CourseDetail
    detail = CourseDetail.model_validate_json(
        (FIX / "course-multi-syllabus.json").read_text(encoding="utf-8"))
    first, second = (s.weekly_progress.weeks[0].topics[0] for s in detail.syllabi)
    assert first != second


# ----------------------------------------------------------------- 規則 (d) 行事曆錨點

def _numbered(rows=18, midterm_at=9, final_at=None):
    def cell(i):
        if i == midterm_at: return "期中考"
        if i == final_at: return "期末考"
        return f"主題{i}"
    return "\n".join(f"{i}\t{cell(i)}" for i in range(1, rows + 1))


def test_rule_d_accepts_when_midterm_lands_on_the_calendar_week(term):
    """115-1 的期中考在第 9 週。純編號清單的第 9 列剛好寫「期中考」→ 首欄就是週次。
    這個佐證來自完全獨立的來源（校方行事曆），與規則 (b) 是同一個雙證人精神。"""
    rows = parse_anchored_numbered_list(_numbered(midterm_at=9), term)
    assert rows is not None and len(rows) == 18
    assert rows[0][0] == 1 and rows[8][2] == "期中考"


def test_rule_d_accepts_a_16_week_plan(term):
    assert len(parse_anchored_numbered_list(_numbered(rows=16, midterm_at=9), term)) == 16


@pytest.mark.parametrize("text,why", [
    (_numbered(midterm_at=7), "期中考寫在第 7 列，與行事曆的第 9 週對不上"),
    (_numbered(rows=14, midterm_at=None), "14 列、無期中考——列數落在背景區間，沒有證據"),
    (_numbered(rows=8, midterm_at=None), "列數不足"),
    ("\n".join(f"{i}. 單元{i}（2 months）" for i in range(1, 7)), "月份不是週次，且列數不足"),
])
def test_rule_d_rejects(term, text, why):
    assert parse_anchored_numbered_list(text, term) is None, why


def test_rule_d_rejects_misaligned_even_though_a_number_matches(term):
    """寫了期中考但不在對應那一列 → 首欄很可能是「第幾次上課」或章節編號。
    實測有一份把 Mid Term Exam 寫在第 7 列，不能因為別處對得上就收。"""
    assert parse_anchored_numbered_list(_numbered(midterm_at=7, final_at=15), term) is None


def test_rule_d_only_uses_midterm_not_final(term):
    """期末考錨點**不可靠**：115-1 全量掃過，期末考落在行事曆對應週的偏移分布，
    峰值在 +1（82 筆）與 +3（53 筆）、剛好只有 16 筆——因為考期橫跨第 15、16 週，
    而且很多教師把「期末」寫在最後一列。所以只有期末考對上不足以採信。"""
    # 用 14 列（列數證據不成立）隔離出「只有期末考對上」這個情境
    assert parse_anchored_numbered_list(
        _numbered(rows=14, midterm_at=None, final_at=15), term) is None


def test_rule_d_requires_a_contiguous_sequence_from_one(term):
    text = "\n".join(f"{i}\t{'期中考' if i == 9 else f'主題{i}'}"
                     for i in list(range(1, 9)) + list(range(10, 20)))
    assert parse_anchored_numbered_list(text, term) is None


# ----------------------------------------------------------------- 規則 (e) 跨行 marker

def test_rule_e_joins_marker_only_line_with_the_next():
    """來源是表格的儲存格換行變成文字換行——週次其實明確寫著，
    是我們原本只在同一行找主題而漏抓。這是修 bug，不是放寬判準。"""
    segments = parse_schedule("第1週\n09/10 課程內容簡介 Course Overview\n第2週\n09/17 晶體結構").segments
    assert [(s.start_week, s.topic) for s in segments] == \
        [(1, "課程內容簡介 Course Overview"), (2, "晶體結構")]


def test_rule_e_strips_a_leading_date_from_the_joined_topic():
    assert parse_schedule("第3週\n10/01 熱力學").segments[0].topic == "熱力學"


def test_rule_e_does_not_join_when_next_line_has_its_own_marker():
    """`第1週 ⏎ 第2週 導論` 併起來會把導論安到第 1 週。"""
    segments = parse_schedule("第1週\n第2週 導論").segments
    assert [(s.start_week, s.topic) for s in segments] == [(1, ""), (2, "導論")]


def test_rule_e_handles_english_marker_only_lines():
    segments = parse_schedule("W1\nBasic Concepts of Intelligent Control\nW2\nNeural Networks").segments
    assert [(s.start_week, s.topic) for s in segments] == \
        [(1, "Basic Concepts of Intelligent Control"), (2, "Neural Networks")]


def test_rule_e_leaves_a_trailing_marker_only_line_alone():
    assert [s.topic for s in parse_schedule("第1週 導論\n第2週").segments] == ["導論", ""]


def test_rule_e_does_not_change_the_fixture_baselines():
    """規則 (e) 不得動到 gold／observed 的逐字結果——那兩份是移植保真的證據。"""
    for case in GOLD:
        assert [[s.start_week, s.end_week, s.topic] for s in parse_schedule(case["text"]).segments] \
            == [list(x) for x in case["segments"]], case["name"]


# ----------------------------------------------------------------- 彈性週寬限／體育排除

def test_flexible_weeks_may_be_missing_and_still_resolved(term):
    """115-1 的第 17、18 週是彈性學習週，教師常不排課或放進彈休區域。1~16 週齊全就算完整。"""
    assert build_weekly_progress("\n".join(f"第{i}週 主題{i}" for i in range(1, 17)),
                                 18, term).status == "resolved"
    assert build_weekly_progress("\n".join(f"第{i}週 主題{i}" for i in range(1, 18)),
                                 18, term).status == "resolved"


def test_missing_a_teaching_week_is_still_partial(term):
    text = "\n".join(f"第{i}週 主題{i}" for i in range(1, 17) if i != 15)
    assert build_weekly_progress(text, 18, term).status == "partial"


def test_grace_requires_the_term_to_actually_have_flexible_weeks(term):
    """**閘門綁資料，不寫死 {17,18}**：沒有行事曆就沒有寬限——115 以前第 17、18 週是
    正常上課週，套寬限等於把「教師漏排兩週」誤判成完整。"""
    text = "\n".join(f"第{i}週 主題{i}" for i in range(1, 17))
    assert build_weekly_progress(text, 18, None).status == "partial"
    no_flex = term.model_copy(update={"flexible_learning": None})
    assert build_weekly_progress(text, 18, no_flex).status == "partial"


def test_pe_courses_get_no_weekly_progress(term):
    """體育不產逐週進度：進度欄常是「一堂課塞很多活動」，沒有正確答案可抽。
    用 None（我們沒產）而不是 unparsed（教師未提供）——後者是不實陳述。"""
    from models import Syllabus
    from ntut_catalog.parse_progress import attach_weekly_progress, is_progress_excluded
    syllabi = [Syllabus(schedule="\n".join(f"第{i}週 主題{i}" for i in range(1, 19)))]
    attach_weekly_progress(syllabi, term, course_name="體育")
    assert syllabi[0].weekly_progress is None
    assert is_progress_excluded("體育") and not is_progress_excluded("體育行政")

    other = [Syllabus(schedule="第1週 導論")]
    attach_weekly_progress(other, term, course_name="微積分")
    assert other[0].weekly_progress is not None


# ----------------------------------------------------------------- 表格首欄的三種寫法

def test_rows_accept_chinese_numerals(term):
    """表格常見 `週次 / 一 / 二 / 三`（360924、361168、361488）。中文數字在這裡安全——
    陷阱 3 擔心的 `一週`＝時長，但這條只在有額外證據時才被採信。"""
    text = "週次\t單元主題\n" + "\n".join(
        f"{c}\t主題{i}" for i, c in enumerate("一 二 三 四 五 六 七 八 九 十 十一 十二 十三 十四 十五 十六".split(), 1))
    wp = build_weekly_progress(text, 18, term)
    assert wp.status == "resolved" and len(wp.weeks) == 16


def test_rows_expand_merged_ranges(term):
    """`3-4. 主題` 是一列涵蓋兩週。不展開的話序列不連續，整份會被拒（360754）。"""
    text = "週次   單元主題\n1. 導論\n2. 基礎\n3-4. 機器學習\n5-7. 演算法\n8. 期中考\n9-13. 深度學習\n14-15. NLP\n16. 期末考"
    wp = build_weekly_progress(text, 18, term)
    assert [w.week for w in wp.weeks] == list(range(1, 17))
    assert wp.weeks[2].topics == wp.weeks[3].topics == ["機器學習"]


def test_reversed_or_overlong_merged_range_is_skipped(term):
    from ntut_catalog.parse_progress import _numbered_rows
    assert 9 not in _numbered_rows("9-3. 倒置")
    assert _numbered_rows("1-9. 跨太多週") == {}


def test_midterm_tolerance_is_asymmetric(term):
    """當**證據**時要求剛好對上；當**反證**時放寬 ±1——實測偏移 -1 有 33 筆，
    那是教師把期中考辦在官方考試週前一週的正常變異（16 週的課中點就是第 8 週）。"""
    # 差 1：其他證據（列數 16）成立，不否決
    ok = "\n".join(f"{i}. {'期中考' if i == 8 else f'主題{i}'}" for i in range(1, 17))
    assert build_weekly_progress(ok, 18, term).status == "resolved"
    # 差 2：否決（實測那份把 Mid Term Exam 寫在第 7 列的）
    bad = "\n".join(f"{i}. {'期中考' if i == 7 else f'主題{i}'}" for i in range(1, 19))
    assert build_weekly_progress(bad, 18, term).status == "unparsed"


def test_followup_mention_of_midterm_is_not_a_contradiction(term):
    """361326 寫了 `9 Midterm` 與 `10 Review of midterm`，後者是正常的後續提及。
    否決條件不可要求「恰好只有一列命中」。"""
    text = "\n".join(f"{i}\t{ {9:'Midterm', 10:'Review of midterm'}.get(i, f'Topic {i}') }"
                    for i in range(1, 17))
    assert build_weekly_progress(text, 18, term).status == "resolved"


# ----------------------------------------------------------------- 2026-09-18 第二批實測

def test_teacher_disclaimer_no_longer_kills_the_whole_schedule(term):
    """文末一句「教師可視情況做出調整」曾讓 18 週全解析的進度表整份被判 unparsed
    （366876／366838／366828），單週備註「專題演講 (待定)」也一樣（364705）。
    那些是免責註記，不是「這門課沒有進度」。"""
    text = "\n".join(f"第{i}週 主題{i}" for i in range(1, 19)) + "\n※進度與活動將視情況調整。"
    assert build_weekly_progress(text, 18, term).status == "resolved"


@pytest.mark.parametrize("text,why", [
    ("", "空字串"), ("   ", "只有空白"), ("TBA", "短到不可能有內容"),
])
def test_still_unparsed_when_there_is_genuinely_nothing(term, text, why):
    assert build_weekly_progress(text, 18, term).status == "unparsed", why


def test_row_prefix_variants(term):
    from ntut_catalog.parse_progress import _numbered_rows
    assert _numbered_rows("1: 課程介紹")[1] == "課程介紹"              # 冒號（361781）
    assert _numbered_rows("001(09/10)\t課程介紹")[1] == "課程介紹"      # 前導零＋括號日期（361761）
    assert _numbered_rows("一~四\t硬體架構")[4] == "硬體架構"            # 中文 range（361557）


def test_marker_variants(term):
    """`WK-1`（366869）與 `週 01.`（361439）——週字在數字之前。"""
    assert [s.start_week for s in parse_schedule("WK-1 創業管理課程說明").segments] == [1]
    assert parse_schedule("週 02.\t設計實務").segments[0].topic == "設計實務"
    # `Week 1-4` 不受連字號分隔符影響，仍是 range
    segs = parse_schedule("Week 1-4 Introduction").segments
    assert (segs[0].start_week, segs[0].end_week) == (1, 4)


def test_declared_header_outranks_the_midterm_position(term):
    """表頭寫了「週次」就等於教師說明了首欄是什麼，比期中考位置更直接。
    361557 表頭有「週次」、1~18 齊全，只因為教師把期中考辦在第 7 週而整份被丟。"""
    rows = "\n".join(f"{i}\t{'期中考' if i == 7 else f'主題{i}'}" for i in range(1, 19))
    assert build_weekly_progress("週次\t名稱\n" + rows, 18, term).status == "resolved"
    # 沒有表頭宣告時，差 2 週仍然否決
    assert build_weekly_progress(rows, 18, term).status == "unparsed"
