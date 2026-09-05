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


@pytest.mark.parametrize("raw,cat,online", [
    ("基礎", "基礎", False), ("核心", "核心", False), ("總整", "總整", False),
    ("進階", "進階", False), ("應用", "應用", False),
    ("核e", "核心", True), ("e基", "基礎", True),
    ("＊", None, False), ("", None, False), ("(e)", None, True),
])
def test_normalize_mprogram_category(raw, cat, online):
    assert normalize_mprogram_category(raw) == (cat, online)


# ── 2026-09 上游改版防護（#43）──
# 兩個 fixture 都由真實的 cprog_-4_mprogram_av2.html 衍生，只動要測的那一處。

def test_rules_ignores_decoy_table_before_anchor():
    """錨點之前的干擾單欄表不得被選中——即使它比真正的規定文字更長。

    舊實作是「全頁最長單一 td 表」，這個 fixture 就是它的反例：頁面上方多一則
    比規定內容更長的公告，舊法會回公告、新法靠「相關規定」錨點只看其後的表。
    """
    html = (FIXTURES / "cprog_-4_decoy_table.html").read_text(encoding="utf-8")

    # 防呆：干擾表必須比真規定長，否則舊啟發式（取最長）本來就會選對、這個測試變空砲。
    from bs4 import BeautifulSoup
    singles = [" ".join(t.get_text().split())
               for t in BeautifulSoup(html, "html5lib").find_all("table")
               if len(t.find_all("td")) == 1]
    assert len(singles) == 2 and max(map(len, singles)) == len(
        next(x for x in singles if "維護期間" in x)), "fixture 失效：干擾表不再是最長的那個"

    rules = parse_cprog_rules(html)
    assert rules is not None
    assert "微學程設置定義" in rules            # 真正的規定內容
    assert "維護期間" not in rules              # 干擾公告


def test_rules_ambiguous_after_anchor_returns_none():
    """錨點之後有兩個以上候選 → 回 None，不猜。

    注意：上游是未閉合標籤的老式 HTML（29 個 <tr> 只有 1 個 </tr>、沒有 </body>），
    字串插入會失效，必須經 html5lib 正規化後再改 DOM。
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup((FIXTURES / "cprog_-4_mprogram_av2.html").read_text(encoding="utf-8"),
                         "html5lib")
    extra = BeautifulSoup(
        "<table><tr><td>" + ("填充文字，長度必須超過五十字的門檻才會被視為候選。" * 4)
        + "</td></tr></table>", "html5lib").table
    soup.body.append(extra)
    assert parse_cprog_rules(str(soup)) is None


def test_standard_survives_inserted_column():
    """上游在「課程名稱」後插一欄「英語授課」→ 表頭式仍讀到正確欄位。

    位置式解析（符號欄 +2 起算）會整列右移：學分讀成「否」、時數讀成學分……
    而且是**無聲**的錯，這正是本項加固要防的。
    """
    html = (FIXTURES / "cprog_-4_inserted_column.html").read_text(encoding="utf-8")
    std = parse_cprog_standard(html, entry_year=115, matric="H", division="AV2")
    assert len(std.courses) == 27
    phys = next(c for c in std.courses if c.course_code == "1401041")
    assert phys.name_zh == "物理"
    assert phys.credits == 3.0          # 不是插入的「否」
    assert phys.hours == 3.0
    assert phys.notes == "基礎"


def test_standard_falls_back_when_header_missing():
    """表頭整列被拿掉 → 退回位置式解析，仍解得出課程（降級但不掉資料）。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup((FIXTURES / "cprog_-4_mprogram_av2.html").read_text(encoding="utf-8"),
                         "html5lib")
    header_tr = next(tr for tr in soup.find_all("tr")
                     if "學年" in tr.get_text() and "課程編碼" in tr.get_text())
    header_tr.decompose()
    std = parse_cprog_standard(str(soup), entry_year=115, matric="H", division="AV2")
    assert len(std.courses) == 27
    assert next(c for c in std.courses if c.course_code == "1401041").credits == 3.0
