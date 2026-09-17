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
    pair_bilingual,
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


def test_rule_a_merges_language_variants():
    paired = pair_bilingual([_seg("機構之運動"), _seg("Kinematics of Mechanisms")])
    assert [s.topic for s in paired] == ["機構之運動", "Kinematics of Mechanisms"]  # CJK 在前


def test_rule_a_merges_regardless_of_input_order():
    a = pair_bilingual([_seg("機構之運動"), _seg("Kinematics of Mechanisms")])
    b = pair_bilingual([_seg("Kinematics of Mechanisms"), _seg("機構之運動")])
    assert [s.topic for s in a] == [s.topic for s in b]


@pytest.mark.parametrize("topics,why", [
    (["機構之運動", "剛體運動學"], "兩者同語系"),
    (["Kinematics", "Dynamics"], "兩者同語系"),
    (["機構之運動", ""], "任一 topic 為空"),
    (["機構之運動", "Kinematics", "第三個"], "候選 ≥ 3"),
    (["機構之運動", "Ch.3 機構"], "拉丁那筆含 CJK，不是純語言變體"),
])
def test_rule_a_rejects(topics, why):
    assert pair_bilingual([_seg(t) for t in topics]) is None, why


def test_rule_a_does_not_downgrade_status(term):
    """使用者實測第 2 門課中英各寫一遍、18 週全部 ambiguous —— 這條就能全數救回。"""
    text = "\n".join(f"第{i}週 主題{i}\nWeek {i}: Topic {i}" for i in range(1, 19))
    wp = build_weekly_progress(text, 18, term)
    assert wp.status == "resolved"
    assert len(wp.weeks) == 18
    assert wp.weeks[2].topics == ["主題3", "Topic 3"]
    assert wp.notes == []


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


def test_rule_b_rejects_bare_numbered_list(term):
    """明確拒絕：沒有日期欄佐證的純編號清單。實測第 3 門是 `1.`…`14.`，很可能是章節。
    **連「項數恰等於 week_count」也拒絕**——那只是巧合，一個證據不足以判定。"""
    text = "\n".join(f"{i}. 章節{i}" for i in range(1, 19))
    assert build_weekly_progress(text, 18, term).status == "unparsed"


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


def test_ambiguous_week_is_skipped_with_a_note(term):
    """其餘 ambiguous **不寫進 weeks**，在 notes 留一行、該週視為 missing、status 降 partial。
    App 的版位是一行「本週：主題」，多候選在那裡沒有正確的呈現方式。"""
    wp = build_weekly_progress("第1週 導論\n第3週 主題A\n第3週 主題B", 18, term)
    assert wp.status == "partial"
    assert [w.week for w in wp.weeks] == [1]
    assert wp.notes == ["第 3 週有 2 個無法判定的候選，已略過"]


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
    assert ambiguous <= 800           # POC 734；規則 (e) 讓少數週多出候選，不得失控


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
    assert coverage >= 0.628, f"coverage {coverage:.4f} 低於規則 (a)~(e) 應達到的水準"
    assert cell_rate >= 0.555, f"cell_rate {cell_rate:.4f} 低於規則 (a)~(e) 應達到的水準"


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
    (_numbered(midterm_at=None), "通篇沒有期中考，沒有證據"),
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
    assert parse_anchored_numbered_list(_numbered(midterm_at=None, final_at=15), term) is None


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
