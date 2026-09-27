"""manifest `term_schedule`（D21）：本學期／網站預設學期的切換時刻表。

窗口來自版控的 2026-09-14 ics 快照（公開的校網行事曆）推導的 115 學年度週次表——
與 season 排程同一份真實資料。
"""
import datetime as dt
import json

import pytest

from models import Manifest, TermSchedule
from ntut_catalog.artifacts import derive
from ntut_catalog.calendar_events import parse_calendar_events
from ntut_catalog.term_calendar import build_all_term_calendars
from ntut_catalog.term_schedule import (
    PRESELECTION_LEAD_DAYS,
    build_term_schedule,
    next_term,
    switch_at,
    term_start,
)
from tests.test_derive import canonical  # noqa: F401  (pytest fixture)
from tests.test_term_calendar import SNAPSHOT_ICS


@pytest.fixture(scope="module")
def calendars():
    events = parse_calendar_events(SNAPSHOT_ICS.read_text(encoding="utf-8"),
                                   today=dt.date(2026, 9, 16)).events
    return build_all_term_calendars(events, ["115-1", "115-2"], "u", "sha")


def _pairs(entries):
    return [(e.term, e.from_) for e in entries]


def T(s):
    return dt.datetime.fromisoformat(s)


def test_term_start_and_next_term():
    assert term_start("115-1").isoformat() == "2026-08-01T00:00:00+08:00"
    assert term_start("115-2").isoformat() == "2027-02-01T00:00:00+08:00"
    assert (next_term("115-1"), next_term("115-2")) == ("115-2", "116-1")


def test_switch_is_the_later_withdrawal_close(calendars):
    """115-1 期中撤選：日間部 11/20 17:00、進修部 11/21 17:00 → 取晚者。"""
    cals = calendars.values()
    assert switch_at("115-1", cals) == T("2026-11-21T17:00:00+08:00")
    assert switch_at("115-2", cals) == T("2027-05-08T17:00:00+08:00")
    assert switch_at("114-2", cals) is None       # 沒有週次表 → 不提前切換


def test_schedule_on_real_115_calendars(calendars):
    sched = build_term_schedule(["114-2", "115-1"] + list(calendars), calendars.values())
    assert _pairs(sched.current) == [
        ("114-2", "2026-02-01T00:00:00+08:00"),
        ("115-1", "2026-08-01T00:00:00+08:00"),
        ("115-2", "2027-02-01T00:00:00+08:00"),
        ("116-1", "2027-08-01T00:00:00+08:00"),   # 115-2 檔裡 116-1 預選的 target_term
    ]
    assert _pairs(sched.default) == [
        ("114-2", "2026-02-01T00:00:00+08:00"),
        ("115-1", "2026-08-01T00:00:00+08:00"),
        ("115-2", "2026-11-21T17:00:00+08:00"),
        ("116-1", "2027-05-08T17:00:00+08:00"),
    ]


def test_fallback_to_preselection_minus_lead_days(calendars):
    """撤選窗口推不出來 → 下學期預選開始 − 14 天。"""
    cals = {k: v.model_copy(deep=True) for k, v in calendars.items()}
    for w_list in (t.enrollment_windows for c in cals.values() for t in c.terms.values()):
        w_list[:] = [w for w in w_list if w.kind != "midterm_withdrawal"]
    assert PRESELECTION_LEAD_DAYS == 14
    assert switch_at("115-1", cals.values()) == T("2026-11-23T00:00:00+08:00")   # 12/07 − 14d
    assert switch_at("115-2", cals.values()) == T("2027-05-10T00:00:00+08:00")   # 05/24 − 14d


def test_no_calendars_means_no_early_switch():
    sched = build_term_schedule(["115-1", "114-2", "bogus"], [])
    assert _pairs(sched.default) == _pairs(sched.current) == [
        ("114-2", "2026-02-01T00:00:00+08:00"), ("115-1", "2026-08-01T00:00:00+08:00")]


def test_entry_serializes_as_from():
    sched = TermSchedule.model_validate(
        {"current": [{"term": "115-1", "from": "2026-08-01T00:00:00+08:00"}], "default": []})
    assert json.loads(sched.model_dump_json(by_alias=True))["current"][0] == {
        "term": "115-1", "from": "2026-08-01T00:00:00+08:00"}


def test_derived_manifest_carries_term_schedule(canonical):  # noqa: F811
    derive(canonical)
    raw = json.loads((canonical / "v1" / "manifest.json").read_text(encoding="utf-8"))
    sched = raw["term_schedule"]
    assert {"term": "115-2", "from": "2026-11-21T17:00:00+08:00"} in sched["default"]
    assert {"term": "116-1", "from": "2027-05-08T17:00:00+08:00"} in sched["default"]
    assert sched["current"][0] == {"term": "115-1", "from": "2026-08-01T00:00:00+08:00"}
    assert Manifest.model_validate(raw).term_schedule.default[0].term == "115-1"
