"""manifest `term_schedule`：「本學期」與「網站預設學期」的切換時刻表（D21）。

- **current（本學期）**：各學期自其**開始日**（台北時間 00:00）起為本學期。開始日＝該學期
  calendar.json 的 `administrative_start`（行事曆事件「學年度第N學期開始」）；沒有 calendar.json
  或該欄位為空 → 固定規則 8/1（上學期）／2/1（下學期）。實務上行事曆就是 8/1、2/1，兩者一致；
  以行事曆為準是為了學校哪天改日期時本學期跟著官方走。
  （`term_calendar._containing_term` 的窗口歸屬學期維持固定規則：那是在「還沒有／正在產生」
  calendar.json 時就要用的，不能反過來依賴它。）
- **default（網站預設顯示的學期）**：本學期；但從本學期的**期中撤選截止**起改為下學期
  （本學期已沒有能改的選課動作，學生接著要排的是下學期）。截止＝本學期 calendar.json 中
  `midterm_withdrawal`（target_term＝本學期）各部別 `end` 取最晚者。推不出撤選窗口 →
  退而用下學期預選（`preselection`，target_term＝下學期）最早的 `start` − 14 天；兩者皆無 →
  不提前切換（等到下學期開始）。

兩張表都是「`from` 起生效」的時間軸，client 取 `from ≤ now` 的最後一筆。
**不讀系統時間**（D11 derive 確定性）：只看 canonical 推導出的 calendar.json 與學期清單。
下學期有沒有 catalog、是不是草案都不影響這裡；「預設學期不在 manifest.terms → 退回本學期」
由 client 端處理（apps/web/src/lib/planner/term-schedule.ts）。
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from models import TermCalendarFile, TermSchedule, TermScheduleEntry
from ntut_catalog.ics import TAIPEI

# 撤選窗口推不出來時的退路：下學期預選開始前幾天切換。
PRESELECTION_LEAD_DAYS = 14

_TERM_RE = re.compile(r"^(\d+)-([12])$")


def _key(term: str) -> Tuple[int, int]:
    m = _TERM_RE.match(term)
    return (int(m.group(1)), int(m.group(2))) if m else (-1, -1)


def next_term(term: str) -> str:
    year, sem = _key(term)
    return f"{year}-2" if sem == 1 else f"{year + 1}-1"


def term_start(term: str, calendars: Iterable[TermCalendarFile] = ()) -> dt.datetime:
    """學期（行政上）開始的時刻（台北 00:00）。

    calendars 裡有該學期的 `administrative_start` → 用它；否則固定規則：
    Y-1 → 西元 Y+1911 年 8/1；Y-2 → Y+1912 年 2/1。
    """
    for cal in calendars:
        academic = cal.terms.get(term)
        if academic is not None and academic.administrative_start:
            d = dt.date.fromisoformat(academic.administrative_start)
            return dt.datetime(d.year, d.month, d.day, tzinfo=TAIPEI)
    year, sem = _key(term)
    if sem == 1:
        return dt.datetime(year + 1911, 8, 1, tzinfo=TAIPEI)
    return dt.datetime(year + 1912, 2, 1, tzinfo=TAIPEI)


def _iso(t: dt.datetime) -> str:
    return t.astimezone(TAIPEI).isoformat(timespec="seconds")


def switch_at(term: str, calendars: Iterable[TermCalendarFile]) -> Optional[dt.datetime]:
    """`term` 期間，網站預設改為下學期的時刻（None＝不提前切換）。"""
    withdrawal_ends: List[dt.datetime] = []
    preselection_starts: List[dt.datetime] = []
    nxt = next_term(term)
    for cal in calendars:
        for academic in cal.terms.values():
            for w in academic.enrollment_windows:
                if w.kind == "midterm_withdrawal" and w.target_term == term:
                    withdrawal_ends.append(dt.datetime.fromisoformat(w.end))
                elif w.kind == "preselection" and w.target_term == nxt:
                    preselection_starts.append(dt.datetime.fromisoformat(w.start))
    if withdrawal_ends:
        return max(withdrawal_ends)
    if preselection_starts:
        return min(preselection_starts) - dt.timedelta(days=PRESELECTION_LEAD_DAYS)
    return None


def _timeline(entries: List[Tuple[dt.datetime, str]]) -> List[TermScheduleEntry]:
    """依時刻排序、合併連續同學期的項目（只留最早那筆）。"""
    out: List[TermScheduleEntry] = []
    for at, term in sorted(entries, key=lambda e: (e[0], _key(e[1]))):
        if out and out[-1].term == term:
            continue
        out.append(TermScheduleEntry(term=term, **{"from": _iso(at)}))
    return out


def build_term_schedule(terms: Iterable[str],
                        calendars: Iterable[TermCalendarFile]) -> TermSchedule:
    """`terms`：要涵蓋的學期（manifest.terms ∪ 有週次表的學期）；`calendars`：所有 calendar.json。

    窗口的 target_term（例如 115-2 檔裡的 116-1 預選）也會納入，讓「切到下學期」有對應的學期。
    """
    calendars = list(calendars)
    universe = {t for t in terms if _TERM_RE.match(t)}
    for cal in calendars:
        for academic in cal.terms.values():
            universe.update(w.target_term for w in academic.enrollment_windows
                            if _TERM_RE.match(w.target_term))
    ordered = sorted(universe, key=_key)
    current = [(term_start(t, calendars), t) for t in ordered]
    default = list(current)
    for t in ordered:
        at = switch_at(t, calendars)
        if at is not None:
            default.append((at, next_term(t)))
    return TermSchedule(current=_timeline(current), default=_timeline(default))


def load_calendars(out_dir: Path) -> Dict[str, TermCalendarFile]:
    """v1/terms/*/calendar.json（全部，不受 manifest.calendars 的兩學年度範圍限制）。"""
    terms_dir = out_dir / "v1" / "terms"
    paths = sorted(terms_dir.glob("*/calendar.json")) if terms_dir.exists() else []
    return {p.parent.name: TermCalendarFile.model_validate_json(p.read_text(encoding="utf-8"))
            for p in paths}
