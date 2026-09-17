"""打外部主機（Google Calendar）的薄 HTTP client。

為什麼不共用 CatalogClient：那支綁死學校——client.py:22 寫死 aps.ntut.edu.tw 的 base_url，
client.py:28,101 靠學校錯誤頁的中文字串判重試（學校的錯誤頁是 HTTP 200）。
那套邏輯拿來打 Google 沒有意義，硬套只會在真正失敗時誤判成成功。

這支只保留有意義的部分：限流、指數退避、明確 UA、UTF-8。
"""
from __future__ import annotations

import logging
import random
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 教務處行事曆－學生版（校網公開）。basic.ics 與 full.ics 內容完全相同（實測同 bytes、
# 同 UID 集合、含 DESCRIPTION/LOCATION 的簽章 md5 亦同），不需要選。
ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "docfuhim9b22fqvp2tk842ak3c%40group.calendar.google.com/public/basic.ics"
)

_UA = "ntutbox-course-crawler/0.1 (+https://github.com/ntutbox; academic calendar mirror)"

# 這個 feed 無 ETag、無 Last-Modified，送 If-Modified-Since 也回 200 全量（實測）。
# 條件式 GET 無效是既成事實，不要浪費一輪往返去試。


class CalendarClient:
    def __init__(
        self,
        delay_range: tuple[float, float] = (0.2, 0.5),
        max_retries: int = 3,
        timeout: float = 60.0,
    ):
        self.delay_range = delay_range
        self.max_retries = max_retries
        self._client = httpx.Client(timeout=timeout, headers={"User-Agent": _UA},
                                    follow_redirects=True)
        self.request_count = 0

    def close(self) -> None:
        self._client.close()

    def fetch_ics(self, url: str = ICS_URL) -> str:
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            time.sleep(random.uniform(*self.delay_range) * (1 if attempt == 0 else 2 ** attempt))
            try:
                resp = self._client.get(url)
                self.request_count += 1
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                # 防呆：日曆的「加入我的日曆」deep link 回 200 + 一張產品行銷 HTML，
                # 不會用 404 或 redirect 告訴你失敗（#181 實測）。接錯會拿到 200 卻零事件。
                if "text/calendar" not in ctype:
                    raise RuntimeError(f"unexpected content-type {ctype!r} (expected text/calendar)")
                text = resp.text
                if "BEGIN:VCALENDAR" not in text:
                    raise RuntimeError("response is not an iCalendar document")
                return text
            except (httpx.HTTPError, RuntimeError) as e:
                last_err = e
                logger.warning("ics attempt %d/%d failed: %s", attempt + 1, self.max_retries + 1, e)
        raise RuntimeError(f"ics fetch failed after {self.max_retries + 1} attempts") from last_err
