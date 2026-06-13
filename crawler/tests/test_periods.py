from pathlib import Path

from models import PERIOD_ORDER, PeriodTable
from ntut_catalog.periods import build_period_table, parse_footer_periods

FIXTURES = Path(__file__).parent / "fixtures"


def test_build_period_table_shape():
    table = build_period_table()
    assert isinstance(table, PeriodTable)
    assert table.timezone == "Asia/Taipei"
    tokens = [p.token for p in table.periods]
    assert tokens == PERIOD_ORDER  # 14 節、固定順序（含中午 N、晚上 A-D）
    assert [p.order for p in table.periods] == list(range(14))


def test_build_period_table_wall_clock():
    by_token = {p.token: p for p in build_period_table().periods}
    assert (by_token["1"].start_hm, by_token["1"].end_hm) == ("08:10", "09:00")
    assert (by_token["N"].start_hm, by_token["N"].end_hm) == ("12:10", "13:00")
    assert (by_token["A"].start_hm, by_token["A"].end_hm) == ("18:30", "19:20")
    assert (by_token["D"].start_hm, by_token["D"].end_hm) == ("21:10", "22:00")


def test_footer_matches_static_table():
    """QueryCourse 回應頁尾的官方節次表須與我們的靜態表一致（來源改了要炸出來）。"""
    html = (FIXTURES / "qc_114-1_csie_day.html").read_text(encoding="utf-8")
    footer = parse_footer_periods(html)
    static = {p.token: (p.start_hm, p.end_hm) for p in build_period_table().periods}
    assert footer == static


def test_footer_missing_returns_empty():
    assert parse_footer_periods("<html><body>nothing</body></html>") == {}
