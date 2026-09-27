"""`active` 學期規則（D19）：current-term ∪ 有即將開始／進行中選課窗口的學期；ACTIVE_TERMS 為明確覆寫。

窗口時刻取自 115 學年度實際行事曆（115-2 網路選課 2026-12-07 起，歸屬被選的 115-2）。
"""
import dataclasses
import datetime as dt

import pytest

from models import AcademicTerm, DateRange, EnrollmentWindow, TermCalendarFile, TermCalendarSource
from ntut_catalog import pipeline, registry
from ntut_catalog.ics import TAIPEI
from ntut_catalog.registry import FetchContext, FetchOutput

WINDOWS = {
    "115-1": [
        ("online_selection", "day", "2026-06-08T00:00:00+08:00", "2026-06-19T17:00:00+08:00"),
        ("add_drop", "day", "2026-09-07T00:00:00+08:00", "2026-09-18T17:00:00+08:00"),
        ("midterm_withdrawal", "day", "2026-10-05T00:00:00+08:00", "2026-11-20T17:00:00+08:00"),
        ("midterm_withdrawal", "evening", "2026-10-05T00:00:00+08:00", "2026-11-21T17:00:00+08:00"),
    ],
    "115-2": [
        ("online_selection", "day", "2026-12-07T00:00:00+08:00", "2026-12-18T17:00:00+08:00"),
        ("online_selection", "evening", "2026-12-07T00:00:00+08:00", "2026-12-19T21:00:00+08:00"),
        ("add_drop", "day", "2027-02-22T00:00:00+08:00", "2027-03-05T17:00:00+08:00"),
        ("midterm_withdrawal", "day", "2027-03-22T00:00:00+08:00", "2027-05-07T17:00:00+08:00"),
    ],
}


def _write_calendars(canonical, windows=WINDOWS):
    for term, ws in windows.items():
        term_cal = AcademicTerm(
            instruction_start="2026-09-07", midterm=DateRange(start="2026-11-01", end="2026-11-07"),
            final_exam=DateRange(start="2027-01-03", end="2027-01-09"), break_start="2027-01-11",
            enrollment_windows=[EnrollmentWindow(kind=k, division=d, start=s, end=e)
                                for k, d, s, e in ws])
        cal = TermCalendarFile(source=TermCalendarSource(url="https://example.invalid/cal.ics",
                                                         content_sha256="0" * 64,
                                                         parsed_at="2026-09-27T00:00:00+08:00",
                                                         parser_version="test"),
                               terms={term: term_cal})
        (canonical / term).mkdir(parents=True, exist_ok=True)
        (canonical / term / "calendar.json").write_text(cal.model_dump_json(), encoding="utf-8")


def _at(y, m, d, h=6):
    return dt.datetime(y, m, d, h, 0, tzinfo=TAIPEI)


@pytest.fixture
def canonical(tmp_path):
    c = tmp_path / "canonical"
    _write_calendars(c)
    return c


def _active(canonical, now, current, env=""):
    return registry.resolve_terms(
        "active", [], lambda: current, active_env=env,
        upcoming=lambda: registry.upcoming_window_terms(canonical, now, registry.SELECTION_LEAD_DAYS))


def test_nov_06_only_current(canonical):
    # 115-2 網路選課 12/07 開始，距 11/06 超過 30 天；115-1 期中撤選進行中但它本來就是 current
    assert registry.upcoming_window_terms(canonical, _at(2026, 11, 6)) == ["115-1"]
    assert _active(canonical, _at(2026, 11, 6), "115-1") == ["115-1"]


def test_nov_08_includes_next_term(canonical):
    # 12/07 00:00 ≤ 11/08 06:00 + 30 天 → 115-2 一起爬（current-term 仍是 115-1）
    assert _active(canonical, _at(2026, 11, 8), "115-1") == ["115-1", "115-2"]


def test_lead_boundary_is_inclusive(canonical):
    assert "115-2" in registry.upcoming_window_terms(canonical, _at(2026, 11, 7, 0))
    assert "115-2" not in registry.upcoming_window_terms(canonical, _at(2026, 11, 6, 23))


def test_during_finals_selection_window(canonical):
    # 115-2 網路選課進行中、115-1 窗口全過：upcoming 只有 115-2，current 仍 115-1
    assert registry.upcoming_window_terms(canonical, _at(2026, 12, 10)) == ["115-2"]
    assert _active(canonical, _at(2026, 12, 10), "115-1") == ["115-1", "115-2"]


def test_after_flip_only_next_term(canonical):
    # 12/19 網路選課結束、學期翻成 115-2；115-2 加退選（2/22）超過 30 天 → 只剩 115-2
    assert registry.upcoming_window_terms(canonical, _at(2027, 1, 5)) == []
    assert _active(canonical, _at(2027, 1, 5), "115-2") == ["115-2"]


def test_active_terms_env_is_explicit_override(canonical):
    called = []
    got = registry.resolve_terms("active", [], lambda: "115-1", active_env="114-2",
                                 upcoming=lambda: called.append(1) or ["115-2"])
    assert got == ["114-2"] and not called
    assert _active(canonical, _at(2026, 11, 8), "115-1", env="115-1") == ["115-1"]


def test_current_rule_ignores_windows(canonical):
    got = registry.resolve_terms("current", [], lambda: "115-1",
                                 upcoming=lambda: ["115-2"])
    assert got == ["115-1"]


def test_broken_or_missing_calendar_is_skipped(tmp_path, canonical):
    (canonical / "115-2" / "calendar.json").write_text("{not json", encoding="utf-8")
    (canonical / "calendar").mkdir()           # 非學期目錄不理會
    assert registry.upcoming_window_terms(canonical, _at(2026, 11, 8)) == ["115-1"]
    assert registry.upcoming_window_terms(tmp_path / "nope", _at(2026, 11, 8)) == []


def test_lead_days_env(monkeypatch):
    monkeypatch.delenv("SELECTION_LEAD_DAYS", raising=False)
    assert registry.selection_lead_days() == 30
    monkeypatch.setenv("SELECTION_LEAD_DAYS", "")
    assert registry.selection_lead_days() == 30
    monkeypatch.setenv("SELECTION_LEAD_DAYS", "45")
    assert registry.selection_lead_days() == 45
    for bad in ("x", "-1"):
        monkeypatch.setenv("SELECTION_LEAD_DAYS", bad)
        with pytest.raises(ValueError):
            registry.selection_lead_days()


def test_pipeline_daily_fetches_upcoming_term(tmp_path, canonical, monkeypatch):
    """pipeline 端：daily（未給 --terms、ACTIVE_TERMS 未設）的 catalog／mprograms 會多跑 115-2。"""
    monkeypatch.delenv("ACTIVE_TERMS", raising=False)
    monkeypatch.delenv("SELECTION_LEAD_DAYS", raising=False)
    fetched = []
    for name in ("catalog", "mprograms"):
        def fake(ctx, term, _name=name):
            fetched.append((_name, term))
            return FetchOutput()
        monkeypatch.setitem(registry.DATASETS, name,
                            dataclasses.replace(registry.DATASETS[name], fetch=fake))
    ctx = FetchContext(tmp_path, now=lambda: _at(2026, 11, 8))
    result = pipeline.run("daily", ["catalog", "mprograms"], [], tmp_path, tmp_path / "stage",
                          ctx=ctx, current_term=lambda: "115-1")
    assert result.ok
    assert fetched == [("catalog", "115-1"), ("catalog", "115-2"),
                       ("mprograms", "115-1"), ("mprograms", "115-2")]
