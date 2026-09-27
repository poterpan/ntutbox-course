"""season 排程（issue #111）：enrollment_windows → 整點觸發時刻表（頻率規則、合併、確定性）。

窗口來自版控的 2026-09-14 ics 快照（公開的校網行事曆）推導的 115 學年度週次表。
"""
import datetime as dt
import json

import pytest

from models import AcademicTerm, EnrollmentWindow
from ntut_catalog.calendar_events import parse_calendar_events
from ntut_catalog.ics import TAIPEI
from ntut_catalog.season_schedule import (
    BASE_INTERVAL_HOURS,
    BURST_HOURS,
    SCHEDULE_REL,
    build_schedule,
    load_schedule,
    summarize,
    window_slots,
    write_season_schedule,
)
from ntut_catalog.term_calendar import build_all_term_calendars, derive_term
from tests.test_term_calendar import SNAPSHOT_ICS


@pytest.fixture(scope="module")
def terms():
    events = parse_calendar_events(SNAPSHOT_ICS.read_text(encoding="utf-8"),
                                   today=dt.date(2026, 9, 16)).events
    return {k: derive_term(events, k) for k in ("115-1", "115-2")}


def T(s):
    return dt.datetime.fromisoformat(s)


def test_frequency_constants():
    assert (BURST_HOURS, BASE_INTERVAL_HOURS) == (24, 3)


def test_window_slots_rules():
    """開啟後 24h 每小時、截止前 24h 每小時、截止補一格、其餘 3 小時對齊 00/03/06…"""
    slots = window_slots(T("2026-10-05T00:00:00+08:00"), T("2026-10-08T17:00:00+08:00"))
    got = {at.isoformat(): r for at, r in slots}
    assert got["2026-10-05T00:00:00+08:00"] == "open-burst"
    assert got["2026-10-05T23:00:00+08:00"] == "open-burst"
    assert "2026-10-06T01:00:00+08:00" not in got                   # 非 3 的倍數
    assert got["2026-10-06T03:00:00+08:00"] == "base"
    assert got["2026-10-07T17:00:00+08:00"] == "close-burst"        # 截止前 24h 起每小時
    assert "2026-10-07T16:00:00+08:00" not in got                   # 24h 之外、非 3 的倍數
    assert got["2026-10-07T15:00:00+08:00"] == "base"
    assert got["2026-10-08T16:00:00+08:00"] == "close-burst"
    assert got["2026-10-08T17:00:00+08:00"] == "close"
    assert max(got) == "2026-10-08T17:00:00+08:00"
    assert all(at.minute == 0 and at.second == 0 for at, _ in slots)
    assert all(at.hour % 3 == 0 for at, r in slots if r == "base")
    assert [at for at, _ in slots] == sorted(at for at, _ in slots)


def test_window_slots_unaligned_start_and_end():
    """09:00 開、20:30 截止（假想）：從 09:00 起算，截止格進位到 21:00。"""
    slots = window_slots(T("2022-01-03T09:30:00+08:00"), T("2022-01-06T20:30:00+08:00"))
    assert slots[0] == (T("2022-01-03T10:00:00+08:00"), "open-burst")
    assert slots[-1] == (T("2022-01-06T21:00:00+08:00"), "close")


def test_115_withdrawal_and_preselection_counts(terms):
    s = summarize(terms)
    w = s[("115-1", "期中撤選")]
    assert (w["first"], w["last"]) == ("2026-10-05T00:00:00+08:00", "2026-11-21T17:00:00+08:00")
    # 約 7 週：3 小時一格 ≈ 376，加上開頭／兩個截止前 24h 的每小時 → 400 出頭（issue 估約 400）
    assert 400 <= w["count"] <= 450
    # 115-2 預選在 115-1 的檔裡，但 key 是被選學期 115-2
    o = s[("115-2", "預選")]
    assert (o["first"], o["last"]) == ("2026-12-07T00:00:00+08:00", "2026-12-19T21:00:00+08:00")
    assert 130 <= o["count"] <= 170                                   # 選課週 2 週約 150 次
    # 115-1 自己的預選（2026-06，發生在 114-2）不在 115 學年度的兩個檔裡
    assert ("115-1", "預選") not in s and ("115-2", "新生預選") not in s
    # 116-1 預選（2027-05-24）在 115-2 的檔裡；116-1 沒有自己的週次表也照排
    p = s[("116-1", "預選")]
    assert (p["first"], p["last"]) == ("2027-05-24T00:00:00+08:00", "2027-06-05T21:00:00+08:00")


def test_preselection_slots_monitor_target_term(terms):
    by_at = {x["at"]: x for x in build_schedule(terms, None)["slots"]}
    assert by_at["2026-12-07T00:00:00+08:00"] == {
        "at": "2026-12-07T00:00:00+08:00", "terms": "115-2", "windows": ["預選"],
        "reason": "open-burst"}
    assert by_at["2027-05-24T00:00:00+08:00"]["terms"] == "116-1"
    assert by_at["2027-03-22T00:00:00+08:00"]["windows"] == ["期中撤選"]
    assert by_at["2027-02-22T00:00:00+08:00"]["windows"] == ["開學後加退選"]


def test_close_slots_for_day_and_evening(terms):
    sched = build_schedule(terms, "sha")
    by_at = {x["at"]: x for x in sched["slots"]}
    # 115-2 預選：日間部 12/18 17:00、進修部 12/19 21:00 各補一格
    assert by_at["2026-12-18T17:00:00+08:00"]["reason"] == "close"
    assert by_at["2026-12-19T21:00:00+08:00"]["reason"] == "close"
    # 日間部截止之後、進修部截止前 24h 內 → 仍每小時
    assert by_at["2026-12-18T22:00:00+08:00"]["reason"] == "close-burst"
    # 115-1 撤選：日間部 11/20 17:00、進修部 11/21 17:00
    assert by_at["2026-11-20T17:00:00+08:00"] == {
        "at": "2026-11-20T17:00:00+08:00", "terms": "115-1", "windows": ["期中撤選"],
        "reason": "close"}
    assert by_at["2026-11-21T17:00:00+08:00"]["reason"] == "close"
    assert "2026-11-21T18:00:00+08:00" not in by_at


def test_merge_same_hour_across_terms_and_windows():
    """同一整點落在兩個學期／兩個窗口 → 一格，terms 排序串接、windows 聯集、reason 取最具體。"""
    def term(windows):
        return AcademicTerm(instruction_start="2026-09-07", midterm={"start": "x", "end": "x"},
                            final_exam={"start": "x", "end": "x"}, break_start="2027-01-11",
                            enrollment_windows=windows)
    a = EnrollmentWindow(kind="midterm_withdrawal", target_term="115-1", division="day",
                         start="2026-10-05T00:00:00+08:00", end="2026-11-20T17:00:00+08:00")
    b = EnrollmentWindow(kind="preselection", target_term="115-2", division="day",
                         start="2026-11-20T00:00:00+08:00", end="2026-11-27T17:00:00+08:00")
    # 兩個窗口都在 115-1 的檔裡（所在學期），terms 取各自的 target_term
    sched = build_schedule({"115-1": term([b, a])}, None)
    by_at = {x["at"]: x for x in sched["slots"]}
    x = by_at["2026-11-20T17:00:00+08:00"]
    assert x == {"at": "2026-11-20T17:00:00+08:00", "terms": "115-1,115-2",
                 "windows": ["預選", "期中撤選"], "reason": "close"}
    assert by_at["2026-11-20T05:00:00+08:00"]["reason"] == "close-burst"   # 撤選截止前 > 預選開啟
    ats = [x["at"] for x in sched["slots"]]
    assert ats == sorted(ats) and len(ats) == len(set(ats))


def test_schedule_schema(terms):
    sched = build_schedule(terms, "abc")
    assert set(sched) == {"schema_version", "calendar_sha256", "slots"}
    assert sched["schema_version"] == 1 and sched["calendar_sha256"] == "abc"
    for x in sched["slots"]:
        assert set(x) == {"at", "terms", "windows", "reason"}
        assert x["at"].endswith(":00:00+08:00")
        assert x["reason"] in ("open-burst", "close-burst", "close", "base")


def _write_calendars(tmp_path):
    from ntut_catalog.artifacts import write_term_calendar
    events = parse_calendar_events(SNAPSHOT_ICS.read_text(encoding="utf-8"),
                                   today=dt.date(2026, 9, 16)).events
    for key, cal in build_all_term_calendars(events, ["115-1", "115-2"], "u", "sha").items():
        write_term_calendar(cal, key, tmp_path)
    nd = tmp_path / "canonical" / "calendar" / "events.ndjson"
    nd.parent.mkdir(parents=True, exist_ok=True)
    nd.write_text("".join(e.model_dump_json() + "\n" for e in events), encoding="utf-8")


def test_derive_writes_schedule_outside_v1_deterministically(tmp_path):
    from ntut_catalog.artifacts import derive
    _write_calendars(tmp_path)
    manifest = derive(tmp_path)
    assert sorted(manifest.calendars) == ["115-1", "115-2"]
    path = tmp_path / SCHEDULE_REL
    first = path.read_bytes()
    assert not (tmp_path / "v1" / "ops").exists()
    sched = json.loads(first)
    assert sched["calendar_sha256"] and sched["slots"]
    assert {t for x in sched["slots"] for t in x["terms"].split(",")} == {"115-1", "115-2", "116-1"}
    derive(tmp_path)
    assert path.read_bytes() == first                   # 同一份 canonical → 逐位元組相同
    assert load_schedule(tmp_path) == sched


def test_schedule_scope_is_given_host_terms_only(tmp_path):
    """範圍＝給定的**所在學期**的檔；slot terms 是被選學期（115-1 的檔含 115-2 預選）。"""
    _write_calendars(tmp_path)
    write_season_schedule(tmp_path, ["115-1"])
    sched = load_schedule(tmp_path)
    assert {x["terms"] for x in sched["slots"]} == {"115-1", "115-2"}
    write_season_schedule(tmp_path, ["115-2"])
    assert {x["terms"] for x in load_schedule(tmp_path)["slots"]} == {"115-2", "116-1"}
    write_season_schedule(tmp_path, [])
    assert load_schedule(tmp_path)["slots"] == []


def test_slot_times_are_taipei(terms):
    sched = build_schedule(terms, None)
    assert all(T(x["at"]).utcoffset() == dt.timedelta(hours=8) for x in sched["slots"])
    assert all(T(x["at"]).tzinfo is not None for x in sched["slots"])
    assert TAIPEI.utcoffset(None) == dt.timedelta(hours=8)
