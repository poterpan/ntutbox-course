"""微學程（SearchMProgram）+ 課程標準（Cprog）HTML 解析。

Cprog -4 葉節點無 <th>，採位置式但以「符號 + 課程編碼樣式」辨識有效列（防呆 header/footer）。
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from models import ProgramStandard, Requirement, StandardCourse
from ntut_catalog.requirement_legend import build_requirement

_REQ_SYMBOLS = set("○△☆●▲★")
_COURSE_CODE_RE = re.compile(r"^[0-9A-Z]{6,7}$")


def _clean(t: str) -> str:
    return t.replace("　", " ").replace("\xa0", " ").strip()


def _links_with_param(html: str, jsp: str, target_format: str, param: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html, "html5lib")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if jsp not in href:
            continue
        qs = parse_qs(urlparse(href).query)
        if qs.get("format", [""])[0] != target_format:
            continue
        val = qs.get(param, [""])[0]
        if val and val not in seen:
            seen.add(val)
            out.append((val, _clean(a.get_text())))
    return out


def parse_mprogram_list(html: str) -> List[Tuple[str, str]]:
    """SearchMProgram format=-1 → [(學程碼, 名稱)]（連結指向 format=-2）。"""
    return _links_with_param(html, "SearchMProgram.jsp", "-2", "code")


def parse_cprog_matrics(html: str) -> List[Tuple[str, str]]:
    """Cprog format=-2 → [(學制碼, 名稱)]（連結指向 format=-3）。"""
    return _links_with_param(html, "Cprog.jsp", "-3", "matric")


def parse_cprog_divisions(html: str) -> List[Tuple[str, str]]:
    """Cprog format=-3 → [(系所/學程碼, 名稱)]（連結指向 format=-4）。"""
    return _links_with_param(html, "Cprog.jsp", "-4", "division")


def parse_cprog_standard(html: str, entry_year: int, matric: str, division: str) -> ProgramStandard:
    """Cprog format=-4 葉 → ProgramStandard（位置式 + 符號/編碼辨識）。"""
    soup = BeautifulSoup(html, "html5lib")
    text = soup.get_text()
    title = ""
    m = re.search(r"學年度入學(.*?)課程科目表", text, re.S)
    if m:
        title = _clean(m.group(1))

    courses: List[StandardCourse] = []
    for tr in soup.find_all("tr"):
        cells = [_clean(td.get_text()) for td in tr.find_all("td")]
        # 找出符號欄與編碼欄（符號通常在編碼前一格）
        sym_idx = next((i for i, c in enumerate(cells) if c in _REQ_SYMBOLS), None)
        if sym_idx is None or sym_idx + 1 >= len(cells):
            continue
        code = cells[sym_idx + 1]
        if not _COURSE_CODE_RE.match(code):
            continue
        rest = cells[sym_idx + 2:]
        courses.append(StandardCourse(
            study_year=_to_int(cells[sym_idx - 2]) if sym_idx >= 2 else None,
            study_sem=_to_int(cells[sym_idx - 1]) if sym_idx >= 1 else None,
            requirement=build_requirement(cells[sym_idx]),
            course_code=code,
            name_zh=rest[0] if len(rest) > 0 else "",
            credits=_to_float(rest[1]) if len(rest) > 1 else None,
            hours=_to_float(rest[2]) if len(rest) > 2 else None,
            stage=rest[3] if len(rest) > 3 and rest[3] else None,
            group_id=rest[4] if len(rest) > 4 and rest[4] else None,
            notes=rest[5] if len(rest) > 5 else "",
        ))
    return ProgramStandard(entry_year=entry_year, matric=matric, division=division,
                           title=title, courses=courses)


def parse_cprog_rules(html: str) -> Optional[str]:
    """Cprog -4 葉頁「相關規定」→ 純文字（保留換行）。

    結構特徵定位（禁位置索引）：恰含一個 <td> 且純文字最長的 table；
    <br> → 換行；長度 <50 字視為不存在 → None。
    """
    soup = BeautifulSoup(html, "html5lib")
    best: Optional[str] = None
    for table in soup.find_all("table"):
        tds = table.find_all("td")
        if len(tds) != 1:
            continue
        td = tds[0]
        for br in td.find_all("br"):
            br.replace_with("\n")
        lines = [ln.strip() for ln in td.get_text().splitlines()]
        text = "\n".join(ln for ln in lines if ln)
        if len(text) >= 50 and (best is None or len(text) > len(best)):
            best = text
    return best


def _to_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _to_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


_MPROG_CATEGORY_BY_PREFIX = {"基": "基礎", "核": "核心", "總": "總整", "進": "進階", "應": "應用"}


def normalize_mprogram_category(notes: str) -> tuple[Optional[str], bool]:
    """微學程 notes 欄 → (category, online)。無法辨識 → (None, online)；勿猜。

    notes 含 e＝線上課程（ewant 平台；2026-07-19 經課程規劃書+創新學院清單確證，非 EMI）。
    """
    raw = (notes or "").strip()
    letters = re.sub(r"[^A-Za-z]", "", raw)
    online = "e" in letters.lower()
    rest = re.sub(r"[A-Za-z()（）]", "", raw).strip()
    if not rest:
        return None, online
    cat = _MPROG_CATEGORY_BY_PREFIX.get(rest[0])
    return cat, online
