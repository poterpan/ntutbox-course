"""Subj.jsp 解析：format=-2 系所清單、format=-3 某系班級清單。

連結形如 `Subj.jsp?format=-3&year=114&sem=1&code=59`（系所）、
`Subj.jsp?format=-4&...&code=3032`（班級；班級碼 = cwish cunum 命名空間、逐年重編）。
<a> 缺失 → 回空清單，不回退預設值。
"""
from __future__ import annotations

import re
from typing import List, Tuple
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

_FMT = {"departments": "-3", "classes": "-4"}


def _parse_links(html: str, target_format: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html, "html5lib")
    out: List[Tuple[str, str]] = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "Subj.jsp" not in href:
            continue
        qs = parse_qs(urlparse(href).query)
        if qs.get("format", [""])[0] != target_format:
            continue
        code = qs.get("code", [""])[0]
        name = a.get_text(strip=True)
        if code and code not in seen:
            seen.add(code)
            out.append((code, name))
    return out


def parse_departments(html: str) -> List[Tuple[str, str]]:
    """format=-2 頁 → [(系所碼, 系所名)]（頁內連結指向 format=-3）。"""
    return _parse_links(html, _FMT["departments"])


def parse_classes(html: str) -> List[Tuple[str, str]]:
    """format=-3 頁 → [(班級碼, 班級名)]（頁內連結指向 format=-4）。"""
    return _parse_links(html, _FMT["classes"])
