"""逐節點爬取的失敗統計（spec §3「節點失敗的處理」）。

catalog／standards／mprograms／details 都是「一個上游請求＝一個節點」地逐一抓：單一節點在
client 重試 5 次後仍失敗，fetcher **照舊跳過續跑**（不讓一個節點拖垮整輪），但必須把它記下來
回報——否則殘缺的結果會被當成成功、覆寫完整的 canonical 並發佈出去，也不會有任何告警。

`node_total` 是實際嘗試的節點數，merge 用 `len(failed) / node_total` 判斷是否失敗太多。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class NodeTally:
    total: int = 0
    failed: List[Dict[str, object]] = field(default_factory=list)

    def attempt(self) -> None:
        self.total += 1

    def fail(self, **key: object) -> None:
        """記一個失敗節點；`key` 是能在 canonical 裡定位它的欄位（例 `unit="59"`）。"""
        self.failed.append(dict(key))
