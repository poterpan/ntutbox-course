"""Croom.jsp（教室使用表）解析，tag soup → html5lib。

  -2 `Croom.jsp?format=-2&year=Y&sem=S`：全部教室清單（簡稱連結帶 `code=`、全名、容量(座位數)、使用率）
  -3 `Croom.jsp?format=-3&year=Y&sem=S&code=C`：單一教室週課表（日..六 × 節次 1-4,N,5-9,A-D），
     每格可有**多門課**：`(課號) [N人]<BR>課名<BR>班級<BR>`，合開課（大學部／研究所）同格並列。

鐵則（docs/DESIGN.md §4.7 解析防呆）：表頭文字定位欄位、勿寫死索引；缺值 → None、勿回退預設值；
看不懂的格子直接 raise（這間教室記為失敗節點，由 merge 從 HEAD 沿用），不猜。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag

from models import PERIOD_ORDER

_DAY_HEADERS = {"日": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}
_LIST_HEADERS = {"教室簡稱": "raw", "教室全名": "full_name", "容量(座位數)": "capacity"}
_PERIOD_LABEL_RE = re.compile(r"第\s*([0-9A-Z])\s*節")
# 一門課的開頭：`(367018) [1人]`。只認「括號數字＋[..人]」，課名裡的「(一)」「(1)」不會誤中。
_OFFERING_RE = re.compile(r"\((\d+)\)\s*\[[^\]]*人\s*\]")
_BLANK = " \t\r\n　\xa0"


@dataclass
class RoomListRow:
    code: str
    raw: str
    full_name: Optional[str]
    capacity: Optional[int]


def _text(cell: Tag) -> str:
    return cell.get_text(" ", strip=True).strip(_BLANK)


def _header_columns(tr: Tag) -> Dict[str, int]:
    """表頭列 th 文字 → 欄位起始索引（考慮 colspan；只用第一列表頭）。"""
    cols: Dict[str, int] = {}
    i = 0
    for th in tr.find_all(["th", "td"], recursive=False):
        cols.setdefault(re.sub(r"\s+", "", th.get_text()), i)
        i += int(th.get("colspan") or 1)
    return cols


def _find_table(soup: BeautifulSoup, required: Tuple[str, ...]) -> Optional[Tuple[Tag, Dict[str, int]]]:
    for table in soup.find_all("table"):
        first = table.find("tr")
        if first is None:
            continue
        cols = _header_columns(first)
        if all(h in cols for h in required):
            return table, cols
    return None


def parse_room_list(html: str) -> Tuple[List[RoomListRow], List[str]]:
    """-2 清單 → (教室列, 警告)。找不到表頭 → raise（上游改版或錯誤頁，整個資料集失敗）。

    簡稱沒有 `code=` 連結的列無法抓課表 → 跳過並記警告（不編造 code）。
    """
    soup = BeautifulSoup(html, "html5lib")
    found = _find_table(soup, tuple(_LIST_HEADERS))
    if found is None:
        raise ValueError("Croom -2：找不到「教室簡稱／教室全名／容量(座位數)」表頭")
    table, cols = found
    idx = {field: cols[h] for h, field in _LIST_HEADERS.items()}
    rows: List[RoomListRow] = []
    warnings: List[str] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue                              # 表頭列
        if len(tds) <= max(idx.values()):
            warnings.append(f"Croom -2：欄數不足的列略過：{_text(tr)!r}")
            continue
        name_cell = tds[idx["raw"]]
        raw = _text(name_cell)
        code = _link_code(name_cell)
        if code is None:
            warnings.append(f"Croom -2：{raw!r} 沒有 code= 連結，略過")
            continue
        cap_text = _text(tds[idx["capacity"]])
        rows.append(RoomListRow(
            code=code, raw=raw,
            full_name=_text(tds[idx["full_name"]]) or None,
            capacity=int(cap_text) if cap_text.isdigit() else None,
        ))
    return rows, warnings


def _link_code(cell: Tag) -> Optional[str]:
    a = cell.find("a", href=True)
    if a is None:
        return None
    values = parse_qs(urlparse(a["href"]).query).get("code")
    return values[0].strip() if values and values[0].strip() else None


def parse_room_grid(html: str) -> List[Tuple[int, str, List[str]]]:
    """-3 週課表 → [(day, period, [課號…])]，只列有課的格，依 (day, 節次順序) 排序、課號排序去重。

    找不到「日..六」表頭（錯誤頁「網址格式錯誤」等）、節次標籤不認得、非空格子讀不出課號 → raise。
    全空的課表（這學期沒排課的教室）是合法結果，回傳空 list。
    """
    soup = BeautifulSoup(html, "html5lib")
    found = _find_table(soup, tuple(_DAY_HEADERS))
    if found is None:
        raise ValueError("Croom -3：找不到「日 一 … 六」週課表表頭")
    table, cols = found
    day_cols = {cols[h]: day for h, day in _DAY_HEADERS.items()}
    out: Dict[Tuple[int, str], List[str]] = {}
    seen_periods = 0
    for tr in table.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if not tds:
            continue
        m = _PERIOD_LABEL_RE.search(tds[0].get_text())
        if m is None or m.group(1) not in PERIOD_ORDER:
            raise ValueError(f"Croom -3：不認得的節次列 {_text(tds[0])!r}")
        period = m.group(1)
        seen_periods += 1
        for i, td in enumerate(tds):
            day = day_cols.get(i)
            if day is None:
                continue
            text = td.get_text(" ", strip=True).strip(_BLANK)
            if not text:
                continue
            ids = _OFFERING_RE.findall(text)
            if not ids:
                raise ValueError(f"Croom -3：星期 {day} 第 {period} 節的格子讀不出課號：{text[:80]!r}")
            out[(day, period)] = sorted(set(ids), key=lambda x: (len(x), x))
    if seen_periods == 0:
        raise ValueError("Croom -3：週課表沒有任何節次列")
    order = {p: i for i, p in enumerate(PERIOD_ORDER)}
    return [(d, p, ids) for (d, p), ids in sorted(out.items(), key=lambda kv: (kv[0][0], order[kv[0][1]]))]
