from pathlib import Path

import pytest

from ntut_catalog.parse_course_table import parse_course_rows

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def csie_rows():
    html = (FIXTURES / "qc_114-1_csie_day.html").read_text(encoding="utf-8")
    return parse_course_rows(html)


def test_row_count(csie_rows):
    assert len(csie_rows) == 62


def test_placeholder_like_row_347315(csie_rows):
    """無教師/教室/時段的列：缺 <a> → 空，勿回退。"""
    row = next(r for r in csie_rows if r.offering_id == "347315")
    assert row.name_zh == "體育"
    assert row.course_code == "1004001"
    assert row.classes == [("2798", "資工四")]
    assert row.credits_raw == "1.0"
    assert row.hours_raw == "2"
    assert row.stage_raw == "1"
    assert row.teachers == []
    assert row.classrooms == []
    assert all(not p for p in row.day_periods.values())
    assert row.enrolled_raw == "0"
    assert row.withdrawn_raw == "0"
    assert row.language is None
    assert row.syllabus == []


def test_full_row_347322(csie_rows):
    row = next(r for r in csie_rows if r.offering_id == "347322")
    assert row.name_zh == "嵌入式系統"
    assert row.course_code == "5904319"
    assert row.req_symbol == "★"
    assert row.teachers == [("12384", "張世豪")]
    assert row.classrooms == [("439", "六教527(e)")]
    assert row.day_periods == {0: [], 1: [], 2: [], 3: [], 4: [], 5: ["5", "6", "7"], 6: []}
    assert row.enrolled_raw == "8"
    assert row.withdrawn_raw == "0"
    assert row.language == "英語"
    assert row.syllabus == [("347322", "12384")]
    assert row.notes == "資工四、資工所和電資國際班合開"
    assert row.interdisciplinary == "無人機微學程"


def test_multi_day_meetings_347327(csie_rows):
    row = next(r for r in csie_rows if r.offering_id == "347327")
    assert row.day_periods[2] == ["5", "6"]   # 週二
    assert row.day_periods[3] == ["6"]        # 週三
    assert row.withdrawn_raw == "1"


def test_multi_interdisciplinary_347338(csie_rows):
    row = next(r for r in csie_rows if r.offering_id == "347338")
    assert "人工智慧科技學程" in row.interdisciplinary
    assert "數據分析微學程" in row.interdisciplinary


def test_all_rows_have_offering_id(csie_rows):
    assert all(r.offering_id.isdigit() and len(r.offering_id) == 6 for r in csie_rows)


def test_header_not_found_raises():
    with pytest.raises(ValueError, match="header"):
        parse_course_rows("<html><body><table><tr><td>x</td></tr></table></body></html>")
