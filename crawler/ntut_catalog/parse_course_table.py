"""QueryCourse.jsp 開課清單表格解析（24 欄，tag soup → html5lib）。

鐵則（docs/DESIGN.md §4.7 解析防呆）：
  - **表頭文字定位欄位**，絕不寫死索引（gnehs 寫死索引 → language/ta 雙空 bug）
  - `<a>` 缺失 → 欄位 null/空清單，**勿回退預設值**
  - 備註等原文照存（會混入「一般教室」等教室類別字）
  - 欄數不符 → 整列存 raw_cells 並由呼叫端告警，不硬解
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag

# 表頭文字（normalize 後）→ 邏輯欄位名。星期欄另列。
_HEADER_MAP = {
    "課號": "offering_id",
    "課程名稱": "name",
    "階段": "stage",
    "學分": "credits",
    "時數": "hours",
    "修": "req",
    "班級": "classes",
    "教師": "teachers",
    "教室": "classrooms",
    "人": "enrolled",
    "撤": "withdrawn",
    "授課語言": "language",
    "教學大綱與進度表": "syllabus",
    "備註": "notes",
    "隨班附讀": "audit",
    "實驗實習": "lab",
    "跨領域": "interdisciplinary",
}
# 星期表頭 → Weekday（0=日 … 6=六）
_DAY_HEADERS = {"日": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}

_PERIOD_TOKEN_RE = re.compile(r"[1-9NA-D]")
# 全形 → 半形（節次/數字欄防呆）
_FULLWIDTH = str.maketrans("０１２３４５６７８９ＮＡＢＣＤ", "0123456789NABCD")


@dataclass
class RawCourseRow:
    offering_id: str
    name_zh: str = ""
    course_code: Optional[str] = None          # 課名 cell 的 Curr.jsp?code=（課程編碼，跨學期固定）
    stage_raw: Optional[str] = None
    credits_raw: Optional[str] = None
    hours_raw: Optional[str] = None
    req_symbol: Optional[str] = None
    classes: List[Tuple[str, str]] = field(default_factory=list)      # (班級碼, 班級名)
    teachers: List[Tuple[str, str]] = field(default_factory=list)     # (教師碼, 姓名)
    day_periods: Dict[int, List[str]] = field(default_factory=dict)   # Weekday → 節次 token
    classrooms: List[Tuple[str, str]] = field(default_factory=list)   # (教室碼, 教室名)
    enrolled_raw: Optional[str] = None
    withdrawn_raw: Optional[str] = None
    language: Optional[str] = None
    syllabus: List[Tuple[str, str]] = field(default_factory=list)     # (snum, 教師碼)
    notes: str = ""
    audit: Optional[str] = None
    lab: Optional[str] = None
    interdisciplinary: Optional[str] = None
    raw_cells: List[str] = field(default_factory=list)                # 欄數異常時整列原文


def _clean(text: str) -> str:
    return text.replace("　", " ").strip()


def _links(cell: Tag, jsp: str, code_param: str = "code") -> List[Tuple[str, str]]:
    """cell 內指向某 jsp 的 <a> → [(code, text)]；無 <a> → []（勿回退）。"""
    out = []
    for a in cell.find_all("a", href=True):
        if jsp not in a["href"]:
            continue
        qs = parse_qs(urlparse(a["href"]).query)
        code = qs.get(code_param, [""])[0]
        out.append((code, _clean(a.get_text())))
    return out


def _periods(cell: Tag) -> List[str]:
    text = _clean(cell.get_text()).translate(_FULLWIDTH)
    return _PERIOD_TOKEN_RE.findall(text)


def _text_or_none(cell: Tag) -> Optional[str]:
    t = _clean(cell.get_text())
    return t or None


def _locate_columns(header_cells: List[str]) -> Tuple[Dict[str, int], Dict[int, int]]:
    """表頭文字 → (邏輯欄位→index, Weekday→index)。缺關鍵欄 raise。"""
    col: Dict[str, int] = {}
    day_col: Dict[int, int] = {}
    for i, raw in enumerate(header_cells):
        h = re.sub(r"\s", "", raw)
        if h in _DAY_HEADERS:
            day_col[_DAY_HEADERS[h]] = i
        elif h in _HEADER_MAP:
            col[_HEADER_MAP[h]] = i
    missing = {"offering_id", "name", "classes", "teachers"} - col.keys()
    if missing or len(day_col) != 7:
        raise ValueError(f"course table header not recognized (missing={missing}, days={len(day_col)})")
    return col, day_col


def parse_course_rows(html: str) -> List[RawCourseRow]:
    soup = BeautifulSoup(html, "html5lib")
    header_row = None
    for tr in soup.find_all("tr"):
        ths = tr.find_all("th")
        if ths and any("課號" in th.get_text() for th in ths):
            header_row = tr
            break
    if header_row is None:
        raise ValueError("course table header not found")

    col, day_col = _locate_columns([th.get_text() for th in header_row.find_all("th")])
    expected_cells = len(header_row.find_all("th"))

    rows: List[RawCourseRow] = []
    table = header_row.find_parent("table")
    for tr in header_row.find_next_siblings("tr") if table is None else table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue  # 表頭列
        first = _clean(cells[0].get_text())
        if not re.fullmatch(r"\d{6}", first):
            continue  # 非課程列（說明/合計等）
        if len(cells) != expected_cells:
            rows.append(RawCourseRow(offering_id=first, raw_cells=[str(c) for c in cells]))
            continue

        def cell(name: str) -> Tag:
            return cells[col[name]]

        name_links = _links(cell("name"), "Curr.jsp")
        row = RawCourseRow(
            offering_id=first,
            name_zh=name_links[0][1] if name_links else _clean(cell("name").get_text()),
            course_code=name_links[0][0] if name_links else None,
            stage_raw=_text_or_none(cell("stage")) if "stage" in col else None,
            credits_raw=_text_or_none(cell("credits")) if "credits" in col else None,
            hours_raw=_text_or_none(cell("hours")) if "hours" in col else None,
            req_symbol=_text_or_none(cell("req")) if "req" in col else None,
            classes=_links(cell("classes"), "Subj.jsp"),
            teachers=_links(cell("teachers"), "Teach.jsp"),
            day_periods={d: _periods(cells[i]) for d, i in day_col.items()},
            classrooms=_links(cell("classrooms"), "Croom.jsp") if "classrooms" in col else [],
            enrolled_raw=_text_or_none(cell("enrolled")) if "enrolled" in col else None,
            withdrawn_raw=_text_or_none(cell("withdrawn")) if "withdrawn" in col else None,
            language=_text_or_none(cell("language")) if "language" in col else None,
            syllabus=[
                (parse_qs(urlparse(a["href"]).query).get("snum", [""])[0],
                 parse_qs(urlparse(a["href"]).query).get("code", [""])[0])
                for a in cell("syllabus").find_all("a", href=True)
                if "ShowSyllabus.jsp" in a["href"]
            ] if "syllabus" in col else [],
            notes=_clean(cell("notes").get_text()) if "notes" in col else "",
            audit=_text_or_none(cell("audit")) if "audit" in col else None,
            lab=_text_or_none(cell("lab")) if "lab" in col else None,
            interdisciplinary=(
                _clean(cell("interdisciplinary").get_text(separator="\n")) or None
            ) if "interdisciplinary" in col else None,
        )
        rows.append(row)
    return rows
