from pathlib import Path

from ntut_catalog.client import (
    ALL_MATRIC_CODES,
    SCHOOL_MATRIC,
    build_query_payload,
    parse_current_term,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_current_term_from_querycurrpage():
    html = (FIXTURES / "querycurrpage_tw.html").read_text(encoding="utf-8")
    assert parse_current_term(html) == "115-1"  # year selected=115、sem selected=上學期


def test_parse_current_term_sem_lower():
    html = (
        '<select name="year"><option>114</option><option selected>115</option></select>'
        '<select name="sem"><option value="1">上學期</option>'
        '<option value="2" selected>下學期</option></select>'
    )
    assert parse_current_term(html) == "115-2"


def test_school_matric_literal():
    assert SCHOOL_MATRIC == "'0','1','4','5','6','7','8','9','A','C','D','E','F'"
    assert len(ALL_MATRIC_CODES) == 13


def test_build_query_payload():
    p = build_query_payload(114, 1, "'5'", "＊")
    assert p["year"] == "114" and p["sem"] == "1"
    assert p["matric"] == "'5'" and p["unit"] == "＊"
    assert p["stime"] == "0"                      # 缺了 server 會回錯誤頁
    assert all(p[f"D{d}"] == "ON" for d in range(7))
    assert p["PN"] == "ON" and p["P13"] == "ON"
    assert p["cname"] == "" and p["ccode"] == "" and p["tname"] == ""
