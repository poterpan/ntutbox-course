import re
from pathlib import Path

import pytest

from models import RequirementCategory
from ntut_catalog.parse_program import (
    normalize_mprogram_category,
    parse_cprog_divisions,
    parse_cprog_matrics,
    parse_cprog_rules,
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


def test_parse_cprog_rules_av2():
    html = (FIXTURES / "cprog_-4_mprogram_av2.html").read_text(encoding="utf-8")
    text = parse_cprog_rules(html)
    assert text is not None
    assert "微學程設置定義" in text
    assert "至少修畢8學分" in text.replace(" ", "")
    assert "\n" in text                      # 保留換行
    # 無殘留 HTML tag（來源正文含麵包屑箭頭 "=>"，屬合法原文，不可誤刪）
    assert not re.search(r"<[A-Za-z/][^>]*>", text)


def test_parse_cprog_rules_absent():
    html = (FIXTURES / "cprog_-3_115_7.html").read_text(encoding="utf-8")   # 系所列表頁，無規則區塊
    assert parse_cprog_rules(html) is None


@pytest.mark.parametrize("raw,cat,emi", [
    ("基礎", "基礎", False), ("核心", "核心", False), ("總整", "總整", False),
    ("進階", "進階", False), ("應用", "應用", False),
    ("核e", "核心", True), ("e基", "基礎", True),
    ("＊", None, False), ("", None, False), ("(e)", None, True),
])
def test_normalize_mprogram_category(raw, cat, emi):
    assert normalize_mprogram_category(raw) == (cat, emi)
