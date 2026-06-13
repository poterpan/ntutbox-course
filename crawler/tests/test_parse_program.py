from pathlib import Path

from models import RequirementCategory
from ntut_catalog.parse_program import (
    parse_cprog_divisions,
    parse_cprog_matrics,
    parse_cprog_standard,
    parse_mprogram_list,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_mprogram_list():
    html = (FIXTURES / "mprogram_list_115-1.html").read_text(encoding="utf-8")
    progs = parse_mprogram_list(html)
    assert len(progs) >= 40
    codes = dict(progs)
    assert codes["AV9"] == "人工智慧與深度學習微學程"


def test_parse_cprog_matrics():
    html = (FIXTURES / "cprog_-2_115.html").read_text(encoding="utf-8")
    matrics = parse_cprog_matrics(html)
    codes = dict(matrics)
    assert codes.get("7") == "四技"
    assert codes.get("8") == "碩士班"


def test_parse_cprog_divisions():
    html = (FIXTURES / "cprog_-3_115_7.html").read_text(encoding="utf-8")
    divs = parse_cprog_divisions(html)
    assert len(divs) >= 5
    assert all(code for code, _ in divs)


def test_parse_cprog_standard():
    html = (FIXTURES / "cprog_-4_sample.html").read_text(encoding="utf-8")
    std = parse_cprog_standard(html, entry_year=115, matric="7", division="14F")
    assert "博雅課程" in std.title
    assert len(std.courses) >= 5
    c = next(c for c in std.courses if c.course_code == "1410045")
    assert c.name_zh == "資訊與生活"
    assert c.credits == 2.0
    assert c.requirement.symbol == "△"
    assert c.requirement.category == RequirementCategory.required
    assert c.study_year == 1 and c.study_sem == 1
