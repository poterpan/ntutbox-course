"""節次 ↔ 牆鐘時間（Asia/Taipei）。

權威來源：QueryCourse.jsp 回應頁尾的官方節次表（live 抓取 2026-06-13）。
靜態表 + parse_footer_periods() 雙保險：爬取時用後者驗證來源沒改時刻。
節次 token 順序固定 1-4, N(中午), 5-9, A-D(晚上) —— 不是 1..14。
"""
from __future__ import annotations

import re
from typing import Dict, Tuple

from models import PERIOD_ORDER, PeriodRef, PeriodTable

# token -> (start, end)，來源見 docstring
_WALL_CLOCK: Dict[str, Tuple[str, str]] = {
    "1": ("08:10", "09:00"),
    "2": ("09:10", "10:00"),
    "3": ("10:10", "11:00"),
    "4": ("11:10", "12:00"),
    "N": ("12:10", "13:00"),
    "5": ("13:10", "14:00"),
    "6": ("14:10", "15:00"),
    "7": ("15:10", "16:00"),
    "8": ("16:10", "17:00"),
    "9": ("17:10", "18:00"),
    "A": ("18:30", "19:20"),
    "B": ("19:20", "20:10"),
    "C": ("20:20", "21:10"),
    "D": ("21:10", "22:00"),
}

_FOOTER_RE = re.compile(r"([1-9NA-D]):\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})")


def build_period_table() -> PeriodTable:
    return PeriodTable(
        periods=[
            PeriodRef(
                token=token,
                order=i,
                start_hm=_WALL_CLOCK[token][0],
                end_hm=_WALL_CLOCK[token][1],
                label=token,
            )
            for i, token in enumerate(PERIOD_ORDER)
        ]
    )


def parse_footer_periods(html: str) -> Dict[str, Tuple[str, str]]:
    """抽 QueryCourse 頁尾「各節次上課時間如下」表；找不到回空 dict（不猜）。"""
    anchor = html.find("各節次上課時間")
    if anchor == -1:
        return {}
    return {m.group(1): (m.group(2), m.group(3)) for m in _FOOTER_RE.finditer(html[anchor:])}
