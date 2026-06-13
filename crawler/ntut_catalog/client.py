"""HTTP client：限流（每請求 delay）、指數退避重試、UTF-8。

live 實證（2026-06-13，fixtures 見 tests/fixtures/）：
  - QueryCourse.jsp 必帶 stime（全時段="0"），缺了回「查詢選課資料出現錯誤」
  - matric 值為字面引號列表字串（如 '1','5','6','7','8','9'）；單一碼可獨查
  - unit=＊（全形星號）= 所有系所；server 端不擋大查詢（前端 alert 而已）
  - 錯誤頁也是 HTTP 200 → 以內文判斷重試
"""
from __future__ import annotations

import logging
import random
import re
import time
from typing import Dict, Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://aps.ntut.edu.tw/course/tw/"
ALL_UNITS = "＊"
# 13 個單一學制碼（QueryCurrPage 下拉「全校」實測）
ALL_MATRIC_CODES = ["0", "1", "4", "5", "6", "7", "8", "9", "A", "C", "D", "E", "F"]
SCHOOL_MATRIC = ",".join(f"'{c}'" for c in ALL_MATRIC_CODES)

_ERROR_MARKER = "查詢選課資料出現錯誤"
_UA = "ntutbox-course-crawler/0.1 (+https://github.com/ntutbox; catalog mirror for course planner)"


def parse_current_term(html: str) -> str:
    """讀 QueryCurrPage 下拉的 selected year/sem → 'YYY-S'（比照 gnehs fetchYearSem）。

    無 selected 時退回第一個 option（與瀏覽器預設一致）。
    """
    soup = BeautifulSoup(html, "html5lib")

    def _selected(name: str) -> str:
        sel = soup.find("select", attrs={"name": name})
        if sel is None:
            raise ValueError(f"select[name={name}] not found")
        opt = sel.find("option", selected=True) or sel.find("option")
        if opt is None:
            raise ValueError(f"select[name={name}] has no option")
        return opt.get_text(strip=True)

    year = _selected("year")
    sem_text = _selected("sem")
    sem = 1 if "上" in sem_text else 2
    if not re.fullmatch(r"\d{3}", year):
        raise ValueError(f"unexpected year: {year!r}")
    return f"{year}-{sem}"


def build_query_payload(year: int, sem: int, matric: str, unit: str) -> Dict[str, str]:
    """組 QueryCourse.jsp 表單。matric 直接給字面列表字串（如 \"'5'\" 或 SCHOOL_MATRIC）。"""
    payload = {
        "year": str(year), "sem": str(sem),
        "matric": matric, "unit": unit,
        "cname": "", "ccode": "", "tname": "",
        "stime": "0",  # 全時段；缺此參數 server 回錯誤頁
    }
    for d in range(7):
        payload[f"D{d}"] = "ON"
    for p in ["P1", "P2", "P3", "P4", "PN", "P5", "P6", "P7", "P8", "P9",
              "P10", "P11", "P12", "P13"]:
        payload[p] = "ON"
    return payload


class CatalogClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        delay_range: tuple[float, float] = (0.4, 0.8),
        max_retries: int = 4,
        timeout: float = 60.0,
    ):
        self.base_url = base_url
        self.delay_range = delay_range
        self.max_retries = max_retries
        self._client = httpx.Client(
            base_url=base_url, timeout=timeout, headers={"User-Agent": _UA}
        )
        self.request_count = 0

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kw) -> str:
        """送出 + 限流 + 退避。錯誤頁（200 但含錯誤訊息）也視為可重試失敗。"""
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            time.sleep(random.uniform(*self.delay_range) * (1 if attempt == 0 else 2 ** attempt))
            try:
                resp = self._client.request(method, path, **kw)
                self.request_count += 1
                resp.raise_for_status()
                text = resp.text
                if _ERROR_MARKER in text:
                    raise RuntimeError(f"server error page for {path}")
                return text
            except (httpx.HTTPError, RuntimeError) as e:
                last_err = e
                logger.warning("attempt %d/%d failed: %s", attempt + 1, self.max_retries + 1, e)
        raise RuntimeError(f"request failed after {self.max_retries + 1} attempts: {path}") from last_err

    def query_course(self, year: int, sem: int, matric: str, unit: str) -> str:
        return self._request(
            "POST", "QueryCourse.jsp", data=build_query_payload(year, sem, matric, unit)
        )

    def subj(self, format: str, year: int, sem: int, code: Optional[str] = None) -> str:
        params = {"format": format, "year": str(year), "sem": str(sem)}
        if code is not None:
            params["code"] = code
        return self._request("GET", "Subj.jsp", params=params)

    def query_curr_page(self) -> str:
        return self._request("GET", "QueryCurrPage.jsp")

    def curr(self, code: str) -> str:
        """課程描述頁（中英課名 + 概述），key=課程編碼。"""
        return self._request("GET", "Curr.jsp", params={"format": "-2", "code": code})

    def syllabus(self, snum: str, teacher_code: str) -> str:
        """教學大綱頁，key=(課號 snum, 教師碼)。"""
        return self._request("GET", "ShowSyllabus.jsp", params={"snum": snum, "code": teacher_code})

    def mprogram_list(self, year: int, sem: int) -> str:
        return self._request("GET", "SearchMProgram.jsp",
                             params={"format": "-1", "year": str(year), "sem": str(sem)})

    def mprogram(self, year: int, sem: int, code: str) -> str:
        return self._request("GET", "SearchMProgram.jsp",
                             params={"format": "-2", "year": str(year), "sem": str(sem), "code": code})

    def cprog(self, format: str, **params) -> str:
        """課程標準 Cprog.jsp。format=-2&year / -3&year&matric / -4&year&matric&division。"""
        p = {"format": format, **{k: str(v) for k, v in params.items()}}
        return self._request("GET", "Cprog.jsp", params=p)


def detect_current_term(client: CatalogClient) -> str:
    """打 QueryCurrPage 偵測學校目前預設的學年學期。"""
    return parse_current_term(client.query_curr_page())
