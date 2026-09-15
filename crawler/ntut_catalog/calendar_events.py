"""行事曆事件 feed：ics → 正規化事件 → canonical + horizon 監測。

契約四，見 docs/research/2026-09-06-course-content-and-weekly-progress-handoff.md §5。
換源理由：學校 calModeApp.do 的資料慣例會無預警改變（2026 年起單日全天事件從
end-exclusive 變成 calStart == calEnd），造成過 58 筆事件整批從 App 靜默消失
（poterpan/NTUTBox#180）。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from typing import List, Optional

from models import (
    CALENDAR_SCHEMA_VERSION,
    CalendarEvent,
    CalendarEventsFeed,
    CalendarHorizon,
    CalendarSource,
)
from ntut_catalog.calendar_client import ICS_URL
from ntut_catalog.ics import TAIPEI, parse_ics

logger = logging.getLogger(__name__)

PARSER_VERSION = "calendar-events/1.0.0"

# 上游若改版但仍回 HTTP 200，解析可能得到 0 筆。比照 programs.py:36-40 的既有防呆：
# 拋錯（fail loud），不讓空結果被當成合法結果覆寫並清空既有 canonical。
_MIN_EVENTS = 1
# 相對既有 canonical 的下限，沿用 QUALITY_MIN_RATIO 的精神。
_MIN_RATIO = 0.95


def content_sha256(events: List[CalendarEvent]) -> str:
    """**正規化後**事件集合的雜湊，不是 ics 檔案的 md5。

    VEVENT 排列順序不穩（同一份連抓兩次順序不同，只有 DTSTAMP 與排序變），
    檔案雜湊每次都不同、無法用來判斷有沒有更新。
    """
    payload = "\n".join(e.model_dump_json() for e in events)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def event_start_date(ev: CalendarEvent) -> dt.date:
    raw = ev.start_date or (ev.start_at or "")[:10]
    return dt.date.fromisoformat(raw)


def horizon_required_through(today: dt.date) -> dt.date:
    """feed 至少要涵蓋到哪一天才算健康。

    判準是 `max(DTSTART) >= 次年 6 月`，**不是「有沒有新學年的事件」**——
    112 學年度的下學期拖到 2024-02 才進來，看到新學年不等於整學年到位（#181）。

    分兩段看（學年度 Y 的區間是 Y-08 ~ (Y+1)-07）：
      3~8 月：新學年度的資料**預期**在這段期間出現（實測 112 拖到開學當月的 8 月才上），
              所以這段要求「今年 8 月起跑的那個學年度」已到位 → 涵蓋到 (今年+1)-06。
              這讓提醒從 3 月開始、資料一進來就自動解除。
      9~2 月：不在預期窗口內，只要求**當前**學年度完整，避免整個冬天持續噪音。
    """
    if 3 <= today.month <= 8:
        return dt.date(today.year + 1, 6, 1)
    academic_year = today.year if today.month >= 8 else today.year - 1
    return dt.date(academic_year + 1, 6, 1)


def build_horizon(events: List[CalendarEvent], today: Optional[dt.date] = None) -> CalendarHorizon:
    today = today or dt.datetime.now(TAIPEI).date()
    max_start = max(event_start_date(e) for e in events)
    required = horizon_required_through(today)
    ok = max_start >= required
    if not ok:
        logger.warning(
            "行事曆 horizon 不足：feed 最遠到 %s，應涵蓋到 %s 之後。"
            "新學年度資料尚未匯入（預期 3~8 月出現，最糟會拖到開學當月）。"
            "這不阻斷發布——現有資料沒有壞。",
            max_start, required,
        )
    return CalendarHorizon(max_start=max_start.isoformat(), ok=ok,
                           checked_at=dt.datetime.now(TAIPEI).isoformat(timespec="seconds"))


def parse_calendar_events(
    ics_text: str,
    url: str = ICS_URL,
    previous_count: int = 0,
    today: Optional[dt.date] = None,
) -> CalendarEventsFeed:
    """ics 原文 → CalendarEventsFeed（純函式、不碰檔案、不碰網路）。"""
    events = parse_ics(ics_text)
    if len(events) < _MIN_EVENTS:
        raise ValueError(
            "ics 解析出 0 筆事件——疑似上游改版或接錯端點，中止以保留既有資料"
        )
    if previous_count and len(events) < previous_count * _MIN_RATIO:
        raise ValueError(
            f"ics 解析出 {len(events)} 筆，低於既有 {previous_count} 筆的 "
            f"{_MIN_RATIO:.0%}——疑似上游資料殘缺，中止以保留既有資料"
        )
    now = dt.datetime.now(TAIPEI).isoformat(timespec="seconds")
    logger.info("calendar events: %d 筆（全天 %d / 有時刻 %d）",
                len(events), sum(e.all_day for e in events), sum(not e.all_day for e in events))
    return CalendarEventsFeed(
        source=CalendarSource(url=url, content_sha256=content_sha256(events),
                              fetched_at=now, parser_version=PARSER_VERSION),
        horizon=build_horizon(events, today),
        events=events,
    )


def crawl_calendar_events(client, url: str = ICS_URL, previous_count: int = 0) -> CalendarEventsFeed:
    """抓 + 解析。比照既有慣例：crawl_X(client, key) -> PydanticModel，不碰檔案。"""
    return parse_calendar_events(client.fetch_ics(url), url=url, previous_count=previous_count)
