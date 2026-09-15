"""ics 解析。fixture 涵蓋 #181 驗收條件第 3 條要求的四種事件形態，外加跳脫／折行／
重複 UID／零長度防禦／排序穩定性。"""
from pathlib import Path

import pytest

from ntut_catalog.ics import parse_ics, parse_vevents, sort_key, unescape, unfold

FIXTURE = Path(__file__).parent / "fixtures" / "calendar_sample.ics"


@pytest.fixture(scope="module")
def events():
    return parse_ics(FIXTURE.read_text(encoding="utf-8"))


def by_uid(events, uid):
    return next(e for e in events if e.uid == uid)


def test_all_day_multi_day_converts_end_exclusive_to_inclusive(events):
    # ics DTEND=20261107（end-exclusive）→ inclusive 迄日 11/06
    e = by_uid(events, "multi@google.com")
    assert (e.all_day, e.start_date, e.end_date) == (True, "2026-11-02", "2026-11-06")
    assert e.start_at is None and e.end_at is None


def test_all_day_single_day_end_equals_start(events):
    """#181 驗收：2027/1/11「寒假開始、寒宿開始」。學校 API 把它存成 01/11→01/10
    （結束比開始早一天，無效區間），ics 這邊必須是乾淨的單日。"""
    e = by_uid(events, "single@google.com")
    assert (e.all_day, e.start_date, e.end_date) == (True, "2027-01-11", "2027-01-11")
    assert e.summary == "寒假開始、寒宿開始"


def test_timed_event_converts_utc_to_taipei(events):
    e = by_uid(events, "timed@google.com")
    assert e.all_day is False
    assert (e.start_at, e.end_at) == ("2026-11-02T09:30:00+08:00", "2026-11-02T12:30:00+08:00")
    assert e.start_date is None and e.end_date is None
    assert e.location == "綜合科館" and e.sequence == 2


@pytest.mark.parametrize("uid", ["nodtend@google.com", "nodtend-timed@google.com"])
def test_missing_dtend_falls_back_to_start(events, uid):
    """實測 661 筆中有 4 筆缺 DTEND（都在 2019-2020），parser 必須容忍。"""
    e = by_uid(events, uid)
    assert (e.start_date, e.end_date) == (e.start_date, e.start_date) if e.all_day else True
    assert (e.end_date or e.end_at) == (e.start_date or e.start_at)


def test_zero_length_all_day_defends_to_single_day(events):
    """DTEND == DTSTART 減一天會變成 end < start（無效）。ics 實測 0 筆，但學校 API 有，
    來源哪天學樣時不能產生無效區間。"""
    e = by_uid(events, "zerolen@google.com")
    assert (e.start_date, e.end_date) == ("2027-03-01", "2027-03-01")


def test_text_is_unescaped_but_not_normalized(events):
    e = by_uid(events, "escaped@google.com")
    assert e.summary == "兒童節, 清明節"          # \\, → , （解碼，不是正規化）
    assert e.description.startswith("第一行\n第二行")  # \\n → 換行
    assert "觸發 RFC5545 的行摺疊處理" in e.description  # 折行已還原


def test_duplicate_uid_keeps_newer_revision(events):
    """同 UID 兩筆 → 取 SEQUENCE/LAST-MODIFIED 較新者，不是「第一筆」。"""
    same = [e for e in events if e.uid == "single@google.com"]
    assert len(same) == 1
    assert same[0].summary == "寒假開始、寒宿開始" and same[0].sequence == 3


def test_duplicate_uid_pick_is_order_independent():
    """挑哪一筆**不可以**取決於來源順序——VEVENT 排列每次抓都不同，
    「留第一筆」會讓輸出在有重複時變得不決定性，內容雜湊跟著抖。"""
    text = FIXTURE.read_text(encoding="utf-8")
    head, _, rest = text.partition("BEGIN:VEVENT")
    blocks = ("BEGIN:VEVENT" + rest).split("BEGIN:VEVENT")[1:]
    reversed_text = head + "".join("BEGIN:VEVENT" + b for b in reversed(blocks))
    picked = by_uid(parse_ics(text), "single@google.com")
    picked_rev = by_uid(parse_ics(reversed_text), "single@google.com")
    assert picked.model_dump() == picked_rev.model_dump()


def test_output_is_sorted_and_stable(events):
    """VEVENT 來源順序不穩（同一份連抓兩次順序不同）→ 輸出必須自己定序，
    否則無法用內容雜湊判斷有沒有更新。"""
    assert [sort_key(e) for e in events] == sorted(sort_key(e) for e in events)
    again = parse_ics(FIXTURE.read_text(encoding="utf-8"))
    assert [e.uid for e in again] == [e.uid for e in events]


def test_shuffled_source_order_yields_identical_output():
    """把 VEVENT 區塊反序重組，輸出應逐筆相同。"""
    text = FIXTURE.read_text(encoding="utf-8")
    head, _, rest = text.partition("BEGIN:VEVENT")
    blocks = ("BEGIN:VEVENT" + rest).split("BEGIN:VEVENT")[1:]
    shuffled = head + "".join("BEGIN:VEVENT" + b for b in reversed(blocks))
    assert [e.model_dump() for e in parse_ics(shuffled)] == \
           [e.model_dump() for e in parse_ics(text)]


def test_recurring_events_abort_loudly():
    """RRULE 實測 0 筆。真的出現代表來源改用重複事件，靜默忽略會漏掉整批。"""
    text = FIXTURE.read_text(encoding="utf-8").replace(
        "SUMMARY:期中考試", "RRULE:FREQ=WEEKLY;COUNT=3\r\nSUMMARY:期中考試")
    with pytest.raises(ValueError, match="RRULE"):
        parse_ics(text)


def test_unfold_joins_continuation_lines():
    assert unfold("A:1\r\n B\r\nC:2") == ["A:1B", "C:2"]


def test_unescape_handles_all_rfc5545_escapes():
    assert unescape(r"a\,b\;c\\d\ne") == "a,b;c\\d\ne"


def test_parse_vevents_uppercases_property_names():
    props = parse_vevents("BEGIN:VEVENT\r\nuid:x\r\nEND:VEVENT")[0]
    assert "UID" in props
