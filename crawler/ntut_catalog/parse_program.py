"""微學程（SearchMProgram）+ 課程標準（Cprog）HTML 解析。

Cprog -4 葉節點無 <th>，但**第一列是文字表頭**（學年/學期/類別/課程編碼/…）。
解析以表頭建立「欄名→索引」對照，避免上游插欄/刪欄時整列位移卻無聲讀到錯欄；
表頭認不出來時退回既有的「符號 + 課程編碼樣式」位置式解析並記 warning（見 #43）。
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from models import ProgramStandard, Requirement, StandardCourse
from ntut_catalog.requirement_legend import build_requirement

logger = logging.getLogger(__name__)

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


# 表頭欄名 → StandardCourse 欄位。比對用前綴（上游的「階段別/總階段數」「群組編號(應修學分)」
# 帶斜線與括號、實測還會夾 <br> 與全形空白），故正規化後取 startswith。
_HEADER_FIELDS: tuple[tuple[str, str], ...] = (
    ("學年", "study_year"),
    ("學期", "study_sem"),
    ("類別", "requirement"),
    ("課程編碼", "course_code"),
    ("課程名稱", "name_zh"),
    ("學分", "credits"),
    ("時數", "hours"),
    ("階段別", "stage"),
    ("群組編號", "group_id"),
    ("備註", "notes"),
)
# 少了這些就不算表頭（避免把資料列誤認成表頭）
_HEADER_REQUIRED = {"course_code", "name_zh", "requirement"}


def _header_map(soup) -> Optional[dict]:
    """從第一個看起來像表頭的 <tr> 建「欄位名→索引」。認不出來回 None。"""
    for tr in soup.find_all("tr"):
        cells = [_clean(c.get_text()).replace(" ", "") for c in tr.find_all(["td", "th"])]
        if not cells:
            continue
        idx: dict = {}
        for i, c in enumerate(cells):
            for prefix, field in _HEADER_FIELDS:
                if field not in idx and c.startswith(prefix):
                    idx[field] = i
                    break
        if _HEADER_REQUIRED <= set(idx):
            return idx
    return None


def parse_cprog_standard(html: str, entry_year: int, matric: str, division: str) -> ProgramStandard:
    """Cprog format=-4 葉 → ProgramStandard。

    優先以表頭建立欄名→索引對照：上游插欄/刪欄時整列會位移，位置式解析會**無聲**
    讀到錯欄（學分讀成時數之類），表頭式則自動跟著移動。
    表頭認不出來時退回既有的「符號 + 課程編碼樣式」位置式解析並記 warning。
    兩條路都保留「課程編碼須符合樣式」的防呆，以濾掉 header/footer 雜列。
    """
    soup = BeautifulSoup(html, "html5lib")
    text = soup.get_text()
    title = ""
    m = re.search(r"學年度入學(.*?)課程科目表", text, re.S)
    if m:
        title = _clean(m.group(1))

    hdr = _header_map(soup)
    if hdr is None:
        logger.warning(
            "parse_cprog_standard: 認不出表頭（%s/%s/%s），退回位置式解析（上游可能改版）",
            entry_year, matric, division)

    courses: List[StandardCourse] = []
    for tr in soup.find_all("tr"):
        cells = [_clean(td.get_text()) for td in tr.find_all("td")]
        parsed = (_row_by_header(cells, hdr) if hdr is not None
                  else _row_by_position(cells))
        if parsed is not None:
            courses.append(parsed)
    return ProgramStandard(entry_year=entry_year, matric=matric, division=division,
                           title=title, courses=courses)


def _at(cells: List[str], idx: Optional[int]) -> str:
    return cells[idx] if idx is not None and 0 <= idx < len(cells) else ""


def _row_by_header(cells: List[str], hdr: dict) -> Optional[StandardCourse]:
    code = _at(cells, hdr.get("course_code"))
    if not _COURSE_CODE_RE.match(code):
        return None
    sym = _at(cells, hdr.get("requirement"))
    if sym not in _REQ_SYMBOLS:
        return None
    return StandardCourse(
        study_year=_to_int(_at(cells, hdr.get("study_year"))),
        study_sem=_to_int(_at(cells, hdr.get("study_sem"))),
        requirement=build_requirement(sym),
        course_code=code,
        name_zh=_at(cells, hdr.get("name_zh")),
        credits=_to_float(_at(cells, hdr.get("credits"))),
        hours=_to_float(_at(cells, hdr.get("hours"))),
        stage=_at(cells, hdr.get("stage")) or None,
        group_id=_at(cells, hdr.get("group_id")) or None,
        notes=_at(cells, hdr.get("notes")),
    )


def _row_by_position(cells: List[str]) -> Optional[StandardCourse]:
    """既有的位置式解析：以「符號欄」為原點，編碼在其後一格。表頭認不出時的退路。"""
    sym_idx = next((i for i, c in enumerate(cells) if c in _REQ_SYMBOLS), None)
    if sym_idx is None or sym_idx + 1 >= len(cells):
        return None
    code = cells[sym_idx + 1]
    if not _COURSE_CODE_RE.match(code):
        return None
    rest = cells[sym_idx + 2:]
    return StandardCourse(
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
    )


def _single_td_text(table) -> Optional[str]:
    """恰含一個 <td> 的 table → 其純文字（<br> 轉換行、去空行）；否則 None。"""
    tds = table.find_all("td")
    if len(tds) != 1:
        return None
    td = tds[0]
    for br in td.find_all("br"):
        br.replace_with("\n")
    lines = [ln.strip() for ln in td.get_text().splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return text if len(text) >= 50 else None


def parse_cprog_rules(html: str) -> Optional[str]:
    """Cprog -4 葉頁「相關規定」→ 純文字（保留換行）。

    定位以**語意錨點**為主：頁面上的「相關規定事項：」標題（在 <b><font>、不在表格內），
    只在它**之後**的表格裡找恰含一個 <td> 的表。
      - 恰好一個候選 → 採用
      - 零個 → None（標題在但沒有規定內容）
      - 兩個以上 → None（不猜；上游多長了一塊就該讓人看一眼，而不是賭最長的那個）

    找不到錨點時退回既有的「全頁最長單一 td 表」啟發式並記 warning——該啟發式現行
    49/49 正確，直接回 None 會讓所有學程一起掉資料，比誤判更糟。
    """
    soup = BeautifulSoup(html, "html5lib")
    anchor = soup.find(string=re.compile("相關規定"))
    if anchor is not None:
        cands = [t for t in (_single_td_text(tb) for tb in anchor.find_all_next("table"))
                 if t is not None]
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1:
            logger.warning("parse_cprog_rules: 錨點後有 %d 個候選表格，不猜 → None", len(cands))
        return None

    logger.warning("parse_cprog_rules: 找不到「相關規定」錨點，退回最長單一 td 啟發式（上游可能改版）")
    best: Optional[str] = None
    for table in soup.find_all("table"):
        text = _single_td_text(table)
        if text is not None and (best is None or len(text) > len(best)):
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
