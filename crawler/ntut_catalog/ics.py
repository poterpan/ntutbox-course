"""ics（RFC 5545）解析 → CalendarEvent。來源：校網公開的 Google Calendar。

移植自 docs/research/assets/2026-09-16-calendar-ics-evaluation/scripts/ics_lib.py，
補上型別、逐字反跳脫與 inclusive 日期正規化。

實測（2026-09-14 快照，661 筆 VEVENT）決定的處理方式：
  - **全天事件一律 end-exclusive，無例外**（單日 DTEND-DTSTART==1 天有 393 筆、==0 天 0 筆）
    → 轉 inclusive 時 end = DTEND - 1 天。學校 API 那個零長度壞形態在這裡不存在，
    但仍做防禦：算出 end < start 時退回 end = start。
  - **缺 DTEND 4 筆**（都在 2019-2020）→ end = start。
  - 無 VTIMEZONE、無 TZID；有時刻的事件一律 UTC Z 後綴 → 換算成 +08:00 輸出。
  - RRULE / RECURRENCE-ID / EXDATE 各 0 筆 → 不處理重複展開（真的出現會被 assert 擋下）。
  - **VEVENT 排列順序不穩**（同一份連抓兩次順序不同）→ 輸出一律穩定排序。
  - DTSTAMP 每次抓都變、不帶資訊 → 整個丟掉，provenance 用 LAST-MODIFIED。
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Dict, List, Optional, Tuple

from models import CalendarEvent

logger = logging.getLogger(__name__)

TAIPEI = dt.timezone(dt.timedelta(hours=8))

# name;PARAM=v:value
_Prop = Tuple[Dict[str, str], str]
_RawEvent = Dict[str, List[_Prop]]

_DATE_RE = re.compile(r"\d{8}")
_DATETIME_RE = re.compile(r"(\d{8})T(\d{6})(Z?)")


def unfold(text: str) -> List[str]:
    """RFC 5545 行摺疊還原：以空白/tab 開頭的行是前一行的續行。"""
    out: List[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def unescape(value: str) -> str:
    """RFC 5545 文字反跳脫。這是解碼、不是正規化——summary 的字元本身一個都不動。"""
    out: List[str] = []
    i = 0
    while i < len(value):
        c = value[i]
        if c == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append({"n": "\n", "N": "\n", "\\": "\\", ";": ";", ",": ","}.get(nxt, nxt))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse_vevents(text: str) -> List[_RawEvent]:
    """切出所有 VEVENT。每個 property 存成 {名稱: [(參數, 原始值), ...]}。"""
    events: List[_RawEvent] = []
    cur: Optional[_RawEvent] = None
    for line in unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {}
            continue
        if line == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        name_part, value = line.split(":", 1)
        bits = name_part.split(";")
        params = dict(p.split("=", 1) for p in bits[1:] if "=" in p)
        cur.setdefault(bits[0].upper(), []).append((params, value))
    return events


def _first(ev: _RawEvent, key: str) -> Optional[_Prop]:
    got = ev.get(key)
    return got[0] if got else None


def _text(ev: _RawEvent, key: str) -> Optional[str]:
    got = _first(ev, key)
    return unescape(got[1]) if got else None


def _parse_stamp(prop: _Prop) -> Tuple[Optional[dt.date], Optional[dt.datetime]]:
    """→ (date, None) 表全天；(None, aware datetime) 表有時刻。兩者皆 None 表無法解析。"""
    params, raw = prop
    value = raw.strip()
    if params.get("VALUE", "").upper() == "DATE" or _DATE_RE.fullmatch(value):
        if not _DATE_RE.fullmatch(value):
            return None, None
        return dt.date(int(value[0:4]), int(value[4:6]), int(value[6:8])), None
    m = _DATETIME_RE.fullmatch(value)
    if not m:
        return None, None
    d, t, zulu = m.group(1), m.group(2), m.group(3)
    naive = dt.datetime(int(d[0:4]), int(d[4:6]), int(d[6:8]), int(t[0:2]), int(t[2:4]), int(t[4:6]))
    # Z → UTC 換算成 +08:00；無 Z（floating）→ 依日曆層的 X-WR-TIMEZONE 當作本地時間
    tz = dt.timezone.utc if zulu else TAIPEI
    return None, naive.replace(tzinfo=tz).astimezone(TAIPEI)


def to_event(raw: _RawEvent) -> Optional[CalendarEvent]:
    """單筆 VEVENT → CalendarEvent。缺 UID 或 DTSTART 無法解析 → None（由呼叫端計數）。"""
    uid = _text(raw, "UID")
    dtstart = _first(raw, "DTSTART")
    if not uid or dtstart is None:
        return None
    s_date, s_at = _parse_stamp(dtstart)
    if s_date is None and s_at is None:
        return None

    dtend = _first(raw, "DTEND")
    e_date, e_at = _parse_stamp(dtend) if dtend is not None else (None, None)

    seq = _text(raw, "SEQUENCE")
    common = dict(
        uid=uid,
        summary=_text(raw, "SUMMARY") or "",
        description=_text(raw, "DESCRIPTION") or None,
        location=_text(raw, "LOCATION") or None,
        sequence=int(seq) if seq and seq.strip().isdigit() else None,
        last_modified=_iso_stamp(_first(raw, "LAST-MODIFIED")),
    )

    if s_date is not None:
        # 全天：ics 是 end-exclusive → inclusive 迄日 = DTEND - 1 天；缺 DTEND → 迄日 = 起日
        end = s_date if e_date is None else e_date - dt.timedelta(days=1)
        if end < s_date:      # 防禦：來源若出現零長度/倒置，退回單日而不是產生無效區間
            end = s_date
        return CalendarEvent(all_day=True, start_date=s_date.isoformat(),
                             end_date=end.isoformat(), **common)

    end_at = e_at if e_at is not None else s_at
    return CalendarEvent(all_day=False, start_at=s_at.isoformat(),
                         end_at=end_at.isoformat(), **common)


def _iso_stamp(prop: Optional[_Prop]) -> Optional[str]:
    if prop is None:
        return None
    _, at = _parse_stamp(prop)
    return at.isoformat() if at else None


def _revision_key(ev: CalendarEvent) -> Tuple[int, str, str]:
    """重複 UID 時的挑選鍵。**必須與來源順序無關**——VEVENT 排列每次抓都不同，
    用「留第一筆」會讓輸出在有重複時變得不決定性，內容雜湊也就跟著抖。

    依 RFC 5545，同 UID 且無 RECURRENCE-ID 出現兩次是畸形輸入（實測 661 筆零重複），
    但畸形輸入不該讓整條每日管線停擺，所以取修訂較新者並留 log：
    SEQUENCE 大者優先 → LAST-MODIFIED 新者優先 → 序列化字串較大者（保證全序）。
    """
    return (ev.sequence or -1, ev.last_modified or "", ev.model_dump_json())


def sort_key(ev: CalendarEvent) -> Tuple[str, str, str]:
    """穩定排序鍵。VEVENT 來源順序不穩，輸出必須自己定序才能比對內容有沒有變。"""
    day = ev.start_date or (ev.start_at or "")[:10]
    return (day, ev.start_at or "", ev.uid)


def parse_ics(text: str) -> List[CalendarEvent]:
    """整份 ics → 排序好的事件清單。同 UID 只留第一筆。"""
    raws = parse_vevents(text)
    if any(k in raw for raw in raws for k in ("RRULE", "RECURRENCE-ID", "EXDATE")):
        raise ValueError(
            "ics 出現 RRULE/RECURRENCE-ID/EXDATE——來源開始使用重複事件，"
            "需要先實作展開邏輯才能繼續，中止以免漏掉事件"
        )
    seen: Dict[str, CalendarEvent] = {}
    for raw in raws:
        ev = to_event(raw)
        if ev is None:
            continue
        prev = seen.get(ev.uid)
        if prev is None:
            seen[ev.uid] = ev
        elif _revision_key(ev) > _revision_key(prev):
            logger.warning("ics 出現重複 UID %s，取修訂較新的一筆", ev.uid)
            seen[ev.uid] = ev
    return sorted(seen.values(), key=sort_key)
