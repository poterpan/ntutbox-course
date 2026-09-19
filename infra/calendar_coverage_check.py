"""檢查「已發布的週次表涵蓋哪些學期」——盯的是產物，不是來源。

與 horizon 告警的分工（App 端 2026-09-19 指出的盲點）：

    horizon        量 **ics 來源** 的日期涵蓋到多遠（max(DTSTART) >= 次年 6 月）
    本檔           量 **已產出的 v1 artifact** 涵蓋哪些學期

兩者可以同時成立卻都沒發現問題：2026-09-19 當下 `horizon.ok == true`
（來源涵蓋到 2027-07）與 `terms/115-2/calendar.json` 404（沒上傳）並存。

只告警、不阻斷：每年 8 月新學年度尚未匯入時「缺當前學年度的週次表」是常態，
讓它擋住發佈只會把事件 feed 一起停掉。

用法：python infra/calendar_coverage_check.py [data 目錄]
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))
from ntut_catalog.ics import TAIPEI          # noqa: E402
from ntut_catalog.term_calendar import default_terms  # noqa: E402


def published_terms(out_dir: Path) -> List[str]:
    terms_dir = out_dir / "v1" / "terms"
    if not terms_dir.exists():
        return []
    return sorted(p.parent.name for p in terms_dir.glob("*/calendar.json"))


def term_covering(out_dir: Path, day: dt.date) -> Optional[str]:
    """哪一份已發布的週次表涵蓋了 `day`（含準備週到假期起日之間）。"""
    for term_key in published_terms(out_dir):
        path = out_dir / "v1" / "terms" / term_key / "calendar.json"
        term = json.loads(path.read_text(encoding="utf-8"))["terms"].get(term_key)
        if not term or not term.get("weeks"):
            continue
        first, last = term["weeks"][0]["start"], term["weeks"][-1]["end"]
        if first <= day.isoformat() <= last:
            return term_key
    return None


def run(out_dir: Path, today: Optional[dt.date] = None) -> int:
    today = today or dt.datetime.now(TAIPEI).date()
    published = published_terms(out_dir)
    expected = default_terms(today)
    print(f"已發布週次表的學期：{published or '（無）'}")
    print(f"當前學年度應有：{expected}")

    missing = [t for t in expected if t not in published]
    if missing:
        print(f"::warning title=週次表缺學期::{missing} 尚未發布。"
              f"新學年度的行事曆分批匯入（112 學年度下學期拖到隔年 2 月），"
              f"8~9 月出現這個屬正常；其餘時間出現代表推導或上傳有問題")

    covering = term_covering(out_dir, today)
    if covering:
        print(f"今天（{today}）落在已發布的 {covering} 週次表內")
    else:
        print(f"::warning title=今天沒有對應的週次表::{today} 不在任何已發布週次表的"
              f"授課期間內。學期之間的空窗期屬正常；學期中出現代表 App 的"
              f"「本學期第幾週」會顯示不出來")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    return run(Path(argv[0]) if argv else Path("data"))


if __name__ == "__main__":
    sys.exit(main())
