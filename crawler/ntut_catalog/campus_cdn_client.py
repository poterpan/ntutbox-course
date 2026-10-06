"""讀校園資料平台（ntutbox-campus）公開 CDN 的薄 HTTP client（`campus_gis` 資料集，D28）。

為什麼不共用 CatalogClient／CalendarClient：
- CatalogClient 綁死學校（base_url、靠錯誤頁中文字串判重試）。
- 兩者的 UA 都含 `crawler`——`cdn.ntutbox.com` 的 WAF 擋 UA 含 `bot`／`crawl`／`spider` 的請求
  （回 403，D26），所以這支用**專屬 UA**，不能沿用。

只做：明確 UA、少量重試＋短退避、follow redirects、JSON 回應檢查。驗 sha256 等語意檢查在 fetcher。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

CAMPUS_BASE_URL = "https://cdn.ntutbox.com/campus/v1/"

# 不可含 bot／crawl／spider（不分大小寫）：CDN WAF 會擋（D26）。test_campus_gis 有測。
_UA = "ntutbox-course/0.1 (+https://github.com/ntutbox; campus GIS mirror)"


class CampusCdnClient:
    def __init__(self, base_url: str = CAMPUS_BASE_URL, max_retries: int = 3,
                 backoff: float = 1.0, timeout: float = 60.0):
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.max_retries = max_retries
        self.backoff = backoff
        self._client = httpx.Client(timeout=timeout, headers={"User-Agent": _UA},
                                    follow_redirects=True)
        self.request_count = 0

    def close(self) -> None:
        self._client.close()

    def get_bytes(self, path: str) -> bytes:
        """`base_url + path` 的原始位元組（驗 sha256 要用原始位元組，不能先解碼再編碼）。"""
        url = self.base_url + path.lstrip("/")
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            if attempt:
                time.sleep(self.backoff * 2 ** (attempt - 1))
            try:
                resp = self._client.get(url)
                self.request_count += 1
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                # 防呆：錯誤頁、WAF 擋下時的 HTML 不該被當成資料
                if "json" not in ctype:
                    raise RuntimeError(f"unexpected content-type {ctype!r} (expected JSON)")
                return resp.content
            except (httpx.HTTPError, RuntimeError) as e:
                last_err = e
                logger.warning("campus cdn %s attempt %d/%d failed: %s", path, attempt + 1,
                               self.max_retries, e)
        raise RuntimeError(f"campus cdn fetch {url} failed after {self.max_retries} attempts") from last_err

    def get_json(self, path: str) -> Any:
        return json.loads(self.get_bytes(path))
