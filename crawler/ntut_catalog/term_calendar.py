"""學年度週次表（契約三）：從 ics 具名事件推導 terms/{term}/calendar.json。

**不解析官方 PDF。** 原案是 pdftotext -layout 解 PDF，2026-09-16 推翻——實測顯示
週次表可以只用兩個具名事件推導，111~115 五個學年度、10 個學期逐筆與官方 PDF 週次表相同
（證據：docs/research/assets/2026-09-16-term-week-table-from-ics/）。

兩條規則：
  第 1 週 = 開學日所在的那一週（週日起算）。PDF 把再前一週標「準備」、不給編號。
  末週   = 假期開始日（寒假／暑假開始）前一個週六所在的那一週。
week_count 是**推導出來的**，不是寫死 18；10 個學期都得到 18，不是 18 就讓人來看。

拿掉 PDF 之後，唯一的脆弱點是關鍵字比對（措辭逐年不同）。所以那條被兩件事釘住：
不變量⑧「關鍵字必須恰好命中一筆」，以及不變量⑩「10 個學期逐筆對上校方公告答案」——
而且⑩在**發佈時**跑，不是只在 pytest 跑（本 repo 的 CI 歷史見交接文件 §7）。
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from models import (
    AcademicTerm,
    CalendarEvent,
    DateRange,
    EnrollmentWindow,
    TermCalendarFile,
    TermCalendarSource,
    TermWeek,
)
from ntut_catalog.calendar_events import event_start_date
from ntut_catalog.ics import TAIPEI

logger = logging.getLogger(__name__)

# 1.1.0：新增 enrollment_windows（選課相關窗口，issue #111）；週次表規則不變。
PARSER_VERSION = "calendar/1.1.0"
DERIVED_FIELDS = ["weeks", "preparation", "enrollment_windows"]
WEEK_TABLE_REFERENCE = Path(__file__).parent / "reference" / "pdf-week-tables-111-115.json"

# 「開學」措辭逐年不同（115-1「開學暨註冊截止日、開學典禮」、115-2「開學正式上課、註冊截止日」），
# 含「開學」的候選可能不只一筆 → 優先取含「正式上課」或「註冊」的那筆。
# 111~115 每個學期都收斂到唯一一筆；收斂不到就是不變量⑧失敗，讓人來看，不猜。
_INSTRUCTION = (r"開學", r"正式上課|註冊")
_MIDTERM = (r"期中考試", None)          # 不會誤中「期中撤選」「英文期中會考」
_FINAL = (r"期末考試", None)
_FLEXIBLE = (r"彈性學習週", None)        # 115 學年度才有
_BREAK = (r"寒假開始|暑假開始", None)
_ADMIN = (r"學年度第[12一二]學期開始", None)

# 學制專屬的變體（實測 111-2 的「進修部期末考試(...)」）。全校行事曆取校級那筆。
_DIVISION_QUALIFIER = r"進修部|日間部"


class CalendarDerivationError(ValueError):
    """推導失敗。一律 fail loud——寧可停下來讓人看，也不要發布猜出來的週次表。"""


class TermNotPublishedYet(CalendarDerivationError):
    """該學期的事件還沒進 ics。**這是常態，不是錯誤。**

    新學年度的行事曆由教務處分批匯入，時間沒有固定節奏——112 學年度上學期拖到
    2023-08（開學當月）、下學期更拖到 2024-02。所以每年 8 月 1 日之後的一段期間，
    `default_terms()` 要的新學年度學期在 ics 裡是完全空的。

    這與「有事件但湊不出週次表」必須分開處理：後者代表規則或來源壞了（措辭改了、
    週數不對），要硬錯把人叫來；前者只要安靜跳過，否則每天都失敗，連帶讓
    `crawl-calendar` 非零退出、事件 feed 也一起停更（App 端 2026-09-19 指出）。
    """


def term_window(term_key: str) -> Tuple[dt.date, dt.date]:
    """學期的事件搜尋窗口。學年度 Y 的區間是 Y-08 ~ (Y+1)-07。"""
    year_s, sem_s = term_key.split("-")
    year, sem = int(year_s), int(sem_s)
    if sem == 1:
        return dt.date(year + 1911, 8, 1), dt.date(year + 1912, 1, 31)
    if sem == 2:
        return dt.date(year + 1912, 2, 1), dt.date(year + 1912, 7, 31)
    raise CalendarDerivationError(f"{term_key}: 暑期（sem=3）沒有週次表")


def _in_window(events: Sequence[CalendarEvent], lo: dt.date, hi: dt.date) -> List[CalendarEvent]:
    return [e for e in events if lo <= event_start_date(e) <= hi]


def pick_event(
    events: Sequence[CalendarEvent], term_key: str, spec: Tuple[str, Optional[str]],
    required: bool = True,
) -> Optional[CalendarEvent]:
    """在學期窗口內找**恰好一筆**符合的事件（不變量⑧）。

    0 筆或 ≥2 筆都拋錯（optional 欄位的 0 筆回 None）。**不得靜默取第一筆**——
    那等於在來源措辭改變時悄悄猜一個答案，而週次表錯了 App 整學期都是錯的。
    """
    pattern, prefer = spec
    candidates = [e for e in events if re.search(pattern, e.summary)]
    # 校級的優先於學制專屬的。calendar.json 描述的是全校學期行事曆，
    # 「進修部期末考試(6/17 補行上班，停課一次)」這種是例外附註、不是學期的考試窗口。
    # 實測 111-2 就是這個形狀（兩筆同日）。
    if len(candidates) > 1:
        generic = [e for e in candidates if not re.search(_DIVISION_QUALIFIER, e.summary)]
        if generic:
            candidates = generic
    if len(candidates) > 1 and prefer:
        narrowed = [e for e in candidates if re.search(prefer, e.summary)]
        if narrowed:
            candidates = narrowed
    if not candidates:
        if required:
            raise CalendarDerivationError(
                f"{term_key}: 找不到符合 /{pattern}/ 的事件——來源措辭可能改了，中止")
        return None
    if len(candidates) > 1:
        raise CalendarDerivationError(
            f"{term_key}: /{pattern}/ 命中 {len(candidates)} 筆，無法判定："
            + "、".join(repr(e.summary) for e in candidates)
        )
    return candidates[0]


def _range_of(ev: CalendarEvent) -> DateRange:
    if ev.all_day:
        return DateRange(start=ev.start_date, end=ev.end_date)
    return DateRange(start=ev.start_at[:10], end=(ev.end_at or ev.start_at)[:10])


def sunday_on_or_before(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def saturday_on_or_before(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=(d.weekday() - 5) % 7)


def derive_weeks(instruction_start: dt.date, break_start: dt.date) -> List[TermWeek]:
    """第 1 週＝開學日所在週（週日起算）；末週＝假期開始前一個週六所在週。"""
    first = sunday_on_or_before(instruction_start)
    last = saturday_on_or_before(break_start - dt.timedelta(days=1))
    count = (last - first).days // 7 + 1
    if count < 1:
        raise CalendarDerivationError(
            f"推導出的週數為 {count}：開學日 {instruction_start} 與假期起日 {break_start} 不合理")
    return [
        TermWeek(number=i + 1,
                 start=(first + dt.timedelta(days=7 * i)).isoformat(),
                 end=(first + dt.timedelta(days=7 * i + 6)).isoformat())
        for i in range(count)
    ]


def derive_term(events: Sequence[CalendarEvent], term_key: str) -> AcademicTerm:
    lo, hi = term_window(term_key)
    window = _in_window(events, lo, hi)
    if not window:
        raise TermNotPublishedYet(
            f"{term_key}: 該學期窗口 {lo}~{hi} 內沒有任何事件——新學年度尚未匯入")

    instruction = pick_event(window, term_key, _INSTRUCTION)
    brk = pick_event(window, term_key, _BREAK)
    i_date = event_start_date(instruction)
    b_date = event_start_date(brk)
    weeks = derive_weeks(i_date, b_date)

    prep_start = dt.date.fromisoformat(weeks[0].start) - dt.timedelta(days=7)
    admin = pick_event(window, term_key, _ADMIN, required=False)
    flexible = pick_event(window, term_key, _FLEXIBLE, required=False)
    term = AcademicTerm(
        administrative_start=event_start_date(admin).isoformat() if admin else None,
        preparation=DateRange(start=prep_start.isoformat(),
                              end=(prep_start + dt.timedelta(days=6)).isoformat()),
        instruction_start=i_date.isoformat(),
        weeks=weeks,
        midterm=_range_of(pick_event(window, term_key, _MIDTERM)),
        final_exam=_range_of(pick_event(window, term_key, _FINAL)),
        flexible_learning=_range_of(flexible) if flexible else None,
        break_start=b_date.isoformat(),
    )
    term.enrollment_windows = derive_enrollment_windows(events, window, term_key, term)
    return term


# ----------------------------------------------------------------- 選課相關窗口（issue #111）
#
# 行事曆的寫法逐年不同（空白、全形／半形括號、有無學年度、「17:00 截止」註記、日夜間拆不拆兩筆），
# 所以一律關鍵字＋容錯比對。**推導不出來不讓週次表失敗**——窗口只給 season 排程用，
# 空 list＋warning 就好；週次表錯了 App 整學期都是錯的，這兩者的風險不對等。

_ONLINE_SELECTION = r"網路選課"            # 「新生網路預選」不含「網路選課」，不會誤中
_FRESHMAN = r"新生網路預選"
_ADD_DROP = r"加選及無紀錄退選"
_WITHDRAW_OPEN = r"期中撤選開始"
_WITHDRAW_CLOSE = r"撤選結束"

# 事件沒寫時刻時的截止時間（校方慣例：日間部 17:00、進修部 21:00；未分部別照日間部）
DAY_CLOSE = dt.time(17, 0)
EVENING_CLOSE = dt.time(21, 0)
_DEFAULT_CLOSE = {"day": DAY_CLOSE, "evening": EVENING_CLOSE, "all": DAY_CLOSE}
# 例外：期中撤選的進修部也是 17:00 截止——110～115 學年度凡是寫了時刻的「進修部期中撤選結束」
# 一律 17:00（標題註記或事件時刻），只有沒寫的幾年（111-1、112-1…）才會落到預設，照實證用 17:00。
_KIND_DEFAULT_CLOSE = {"midterm_withdrawal": {"evening": DAY_CLOSE}}

_KIND_ORDER = ("online_selection", "freshman_preselection", "add_drop", "midterm_withdrawal")
_DIVISION_ORDER = ("all", "day", "evening")
_DIVISION_WORD = {"day": "日間部", "evening": "進修部"}
_CN_SEM = {"1": 1, "2": 2, "一": 1, "二": 2}
_TITLE_TERM = re.compile(r"(\d{3})\s*學年度\s*第\s*([12一二])\s*學期|(\d{3})\s*-\s*([12])")
_TITLE_SEM_ONLY = re.compile(r"第\s*([12一二])\s*學期")
_TIME = r"(\d{1,2})\s*[:：]\s*(\d{2})"

# 窗口不變量的容許範圍
ADD_DROP_START_SLACK = dt.timedelta(days=7)      # 加退選開始日距開學日
ADD_DROP_MAX_DAYS = 28                           # 加退選不會超過開學後 4 週


def _divisions(summary: str) -> List[str]:
    return [d for d, word in _DIVISION_WORD.items() if word in summary]


def _start_at(ev: CalendarEvent) -> dt.datetime:
    if ev.all_day:
        return dt.datetime.combine(dt.date.fromisoformat(ev.start_date), dt.time(0), TAIPEI)
    return dt.datetime.fromisoformat(ev.start_at).astimezone(TAIPEI)


def _end_parts(ev: CalendarEvent) -> Tuple[dt.date, Optional[dt.time]]:
    """事件的截止日與時刻（沒寫時刻 → None）。

    有時刻的事件結束在 00:00 → 視為「前一天整天」（ics 的 end-exclusive 寫法），沒有時刻。
    """
    if ev.all_day:
        return dt.date.fromisoformat(ev.end_date or ev.start_date), None
    start = dt.datetime.fromisoformat(ev.start_at).astimezone(TAIPEI)
    end = dt.datetime.fromisoformat(ev.end_at or ev.start_at).astimezone(TAIPEI)
    if end.time() == dt.time(0):
        return (end - dt.timedelta(days=1)).date() if end > start else end.date(), None
    return end.date(), end.time()


def _title_time(summary: str, division: str) -> Optional[dt.time]:
    """標題裡的截止時刻註記：「(日間部 17:00 截止，進修部 21:00 截止)」「(17:00截止)」。"""
    word = _DIVISION_WORD.get(division)
    if word:
        m = re.search(word + r"[^0-9日進]*?" + _TIME, summary)
        if m:
            return dt.time(int(m.group(1)), int(m.group(2)))
    others = [w for d, w in _DIVISION_WORD.items() if d != division]
    if any(w in summary for w in others):
        return None        # 另一個部別的時刻不能拿來用
    m = re.search(_TIME + r"\s*截止", summary)
    return dt.time(int(m.group(1)), int(m.group(2))) if m else None


def _close_at(ev: CalendarEvent, division: str, split: bool, kind: str = "") -> dt.datetime:
    """截止時刻：事件本身的時刻 > 標題註記 > 預設（日 17:00／夜 21:00）。

    一筆事件涵蓋兩個部別（`split`）時，事件的結束時刻是較晚那個（進修部）的，
    日間部改取標題註記或預設。
    """
    day, t = _end_parts(ev)
    if t is not None and not split:
        return dt.datetime.combine(day, t, TAIPEI)
    t2 = _title_time(ev.summary, division)
    if t2 is None and t is not None and division == "evening":
        t2 = t
    default = _KIND_DEFAULT_CLOSE.get(kind, {}).get(division, _DEFAULT_CLOSE[division])
    return dt.datetime.combine(day, t2 or default, TAIPEI)


def _next_term(term_key: str) -> str:
    year, sem = (int(x) for x in term_key.split("-"))
    return f"{year}-2" if sem == 1 else f"{year + 1}-1"


def _containing_term(d: dt.date) -> str:
    """日期所在的學期（term_window：Y-08~(Y+1)-01 為上學期、02~07 為下學期）。"""
    if d.month >= 8:
        return f"{d.year - 1911}-1"
    if d.month == 1:
        return f"{d.year - 1912}-1"
    return f"{d.year - 1912}-2"


def selection_target_term(ev: CalendarEvent) -> str:
    """網路選課事件是在選**哪個學期**的課。

    標題有學年度學期（「115學年度第2學期網路選課」「108-2網路選課」）→ 照標題；
    沒有 → 舉行日期所在學期的**下一學期**（初選在前一學期期末舉行）。
    """
    m = _TITLE_TERM.search(ev.summary)
    if m:
        year = m.group(1) or m.group(3)
        sem = _CN_SEM[m.group(2) or m.group(4)]
        return f"{int(year)}-{sem}"
    return _next_term(_containing_term(event_start_date(ev)))


def _assign_divisions(term_key: str, kind: str, events: Sequence[CalendarEvent],
                      warnings: List[str]) -> List[Tuple[CalendarEvent, str, bool]]:
    """每筆事件 → (事件, 部別, 是否一筆涵蓋兩個部別)。

    標題有部別照標題（兩個都有 → 拆兩個窗口）；沒寫部別的：另一個部別已有明確事件 → 補那個部別；
    兩筆都沒寫 → 較早截止者為日間部、較晚者為進修部；只有一筆 → `all`。同部別出現兩筆 → 不猜、丟棄。
    """
    out: List[Tuple[CalendarEvent, str, bool]] = []
    unqualified: Dict[Tuple, CalendarEvent] = {}
    for ev in events:
        divs = _divisions(ev.summary)
        if divs:
            out += [(ev, d, len(divs) > 1) for d in divs]
        else:
            # 同日期同時刻的重複事件（113-2 有兩筆一模一樣的「期中撤選結束」）只算一筆
            unqualified.setdefault((_start_at(ev), _end_parts(ev)), ev)
    unq = sorted(unqualified.values(), key=lambda e: (_end_parts(e)[0], _start_at(e)))
    taken = {d for _, d, _ in out}
    missing = [d for d in ("day", "evening") if d not in taken]
    if unq:
        if taken and len(unq) <= len(missing):
            out += [(ev, d, False) for ev, d in zip(unq, missing)]
        elif not taken and len(unq) == 2:
            out += [(unq[0], "day", False), (unq[1], "evening", False)]
        elif not taken and len(unq) == 1:
            out.append((unq[0], "all", False))
        else:
            warnings.append(f"{term_key} {kind}: 未標部別的事件無法歸屬："
                            + "、".join(repr(e.summary) for e in unq))
    seen: Dict[str, int] = {}
    for _, d, _ in out:
        seen[d] = seen.get(d, 0) + 1
    dup = sorted(d for d, n in seen.items() if n > 1)
    if dup:
        warnings.append(f"{term_key} {kind}: 部別 {dup} 命中多筆事件，無法判定："
                        + "、".join(repr(e.summary) for e, _, _ in out))
        return []
    return out


def _window(kind: str, division: str, start: dt.datetime, end: dt.datetime,
            uids: Sequence[str]) -> EnrollmentWindow:
    return EnrollmentWindow(kind=kind, division=division,
                            start=start.isoformat(timespec="seconds"),
                            end=end.isoformat(timespec="seconds"),
                            source_uids=list(dict.fromkeys(uids)))


def _simple_windows(term_key: str, kind: str, events: Sequence[CalendarEvent],
                    warnings: List[str]) -> List[EnrollmentWindow]:
    return [_window(kind, d, _start_at(ev), _close_at(ev, d, split, kind), [ev.uid])
            for ev, d, split in _assign_divisions(term_key, kind, events, warnings)]


def _withdrawal_windows(term_key: str, window: Sequence[CalendarEvent],
                        warnings: List[str]) -> List[EnrollmentWindow]:
    """期中撤選：「期中撤選開始」（單日）＋各部別「…撤選結束」（單日）配對成區間。"""
    opens = [e for e in window if re.search(_WITHDRAW_OPEN, e.summary)]
    closes = [e for e in window if re.search(_WITHDRAW_CLOSE, e.summary)]
    if not opens and not closes:
        return []
    if len(opens) != 1 or not closes:
        warnings.append(f"{term_key} midterm_withdrawal: 開始 {len(opens)} 筆、結束 {len(closes)} 筆，"
                        "無法配對")
        return []
    (op,) = opens
    return [_window("midterm_withdrawal", d, _start_at(op),
                    _close_at(ev, d, split, "midterm_withdrawal"),
                    [op.uid, ev.uid])
            for ev, d, split in _assign_divisions(term_key, "midterm_withdrawal", closes, warnings)]


def window_violations(term_key: str, term: AcademicTerm, w: EnrollmentWindow) -> List[str]:
    """單一窗口的不變量（空 list = 通過）。違反者由 derive_enrollment_windows 丟棄並 warning。"""
    bad: List[str] = []
    start, end = dt.datetime.fromisoformat(w.start), dt.datetime.fromisoformat(w.end)
    label = f"{term_key} {w.kind}/{w.division}"
    instr = dt.datetime.combine(dt.date.fromisoformat(term.instruction_start), dt.time(0), TAIPEI)
    last = (dt.datetime.combine(dt.date.fromisoformat(term.weeks[-1].end), dt.time(0), TAIPEI)
            + dt.timedelta(days=1)) if term.weeks else None
    if end <= start:
        bad.append(f"{label}: 截止 {w.end} 不晚於開始 {w.start}")
    if w.kind in ("online_selection", "freshman_preselection") and end > instr:
        bad.append(f"{label}: 截止 {w.end} 晚於開學日 {term.instruction_start}")
    if w.kind == "freshman_preselection" and not term_key.endswith("-1"):
        bad.append(f"{label}: 新生預選只在上學期")
    if w.kind == "add_drop":
        if abs(start - instr) > ADD_DROP_START_SLACK:
            bad.append(f"{label}: 開始 {w.start} 距開學日 {term.instruction_start} 超過 "
                       f"{ADD_DROP_START_SLACK.days} 天")
        if end > instr + dt.timedelta(days=ADD_DROP_MAX_DAYS):
            bad.append(f"{label}: 截止 {w.end} 超過開學後 {ADD_DROP_MAX_DAYS} 天")
    if w.kind == "midterm_withdrawal" and (start < instr or (last and max(start, end) > last)):
        bad.append(f"{label}: {w.start}~{w.end} 不在上課期間 {term.instruction_start}~"
                   f"{term.weeks[-1].end if term.weeks else '?'} 內")
    return bad


def check_window_invariants(term_key: str, term: AcademicTerm) -> List[str]:
    return [v for w in term.enrollment_windows for v in window_violations(term_key, term, w)]


def derive_enrollment_windows(events: Sequence[CalendarEvent], window: Sequence[CalendarEvent],
                              term_key: str, term: AcademicTerm) -> List[EnrollmentWindow]:
    """推導學期的選課相關窗口；推導不出來或違反不變量的窗口丟棄並 warning，不拋錯。

    `events` 是整份 feed（網路選課在前一學期舉行、要跨窗口找），`window` 是本學期窗口內的事件。
    """
    warnings: List[str] = []
    online = [e for e in events if re.search(_ONLINE_SELECTION, e.summary)
              and selection_target_term(e) == term_key]
    found = _simple_windows(term_key, "online_selection", online, warnings)
    found += _simple_windows(term_key, "freshman_preselection",
                             [e for e in window if re.search(_FRESHMAN, e.summary)], warnings)
    found += _simple_windows(term_key, "add_drop",
                             [e for e in window if re.search(_ADD_DROP, e.summary)], warnings)
    found += _withdrawal_windows(term_key, window, warnings)
    keep: List[EnrollmentWindow] = []
    for w in found:
        bad = window_violations(term_key, term, w)
        if bad:
            warnings += bad
        else:
            keep.append(w)
    for msg in warnings:
        logger.warning("選課窗口：%s（該窗口不產出，週次表照常）", msg)
    return sorted(keep, key=lambda w: (w.start, _KIND_ORDER.index(w.kind),
                                       _DIVISION_ORDER.index(w.division)))


def check_invariants(term_key: str, term: AcademicTerm,
                     sibling: Optional[Tuple[str, AcademicTerm]] = None) -> List[str]:
    """回傳違反的不變量描述（空 list = 全過）。編號對應交接文件 §4。

    ⑧（關鍵字唯一性）在 pick_event 直接拋錯，⑨（必填非 null）由 pydantic 結構保證，
    ⑩（10 學期回歸）在 verify_week_table_regression，都不在這裡重複。
    """
    bad: List[str] = []
    weeks = term.weeks
    d = dt.date.fromisoformat

    if len(weeks) != 18:
        bad.append(f"①{term_key}: 推導出 {len(weeks)} 週，不是 18 週")
    for i, w in enumerate(weeks):
        if (d(w.end) - d(w.start)).days != 6:
            bad.append(f"②{term_key}: 第 {w.number} 週長度不是 7 天（{w.start}~{w.end}）")
        if i and (d(w.start) - d(weeks[i - 1].end)).days != 1:
            bad.append(f"②{term_key}: 第 {w.number} 週與前一週不連續")
        if d(w.start).weekday() != 6:
            bad.append(f"③{term_key}: 第 {w.number} 週起日 {w.start} 不是週日")
    if not weeks:
        return bad

    first, last = weeks[0], weeks[-1]
    if not (d(first.start) <= d(term.instruction_start) <= d(first.end)):
        bad.append(f"④{term_key}: 開學日 {term.instruction_start} 不在第 1 週內")
    if not (d(first.start) <= d(term.final_exam.start)
            and d(term.final_exam.end) <= d(last.end)):
        bad.append(f"⑤{term_key}: 期末考 {term.final_exam.start}~{term.final_exam.end} 超出學期範圍")
    if d(term.break_start) <= d(last.end):
        bad.append(f"⑥{term_key}: 假期起日 {term.break_start} 未晚於末週 {last.end}")
    if sibling:
        sib_key, sib = sibling
        a, b = sorted([(term_key, term), (sib_key, sib)], key=lambda kv: kv[0])
        if a[1].weeks and b[1].weeks and d(a[1].weeks[-1].end) >= d(b[1].weeks[0].start):
            bad.append(f"⑦{a[0]} 末週 {a[1].weeks[-1].end} 與 {b[0]} 首週 "
                       f"{b[1].weeks[0].start} 重疊")
    return bad


def load_week_table_reference() -> Dict[str, dict]:
    return json.loads(WEEK_TABLE_REFERENCE.read_text(encoding="utf-8"))


def verify_week_table_regression(events: Sequence[CalendarEvent]) -> List[str]:
    """不變量⑩：對 111~115 十個學期重跑推導，必須與校方公告 PDF 的週次表逐筆相同。

    **這條在發佈時跑**，不是只在 pytest 跑。ics-only 之後它是主要防線：
    來源哪天改措辭、或推導規則被改壞，這裡當天就會紅。
    """
    bad: List[str] = []
    for term_key, expected in sorted(load_week_table_reference().items()):
        try:
            term = derive_term(events, term_key)
        except CalendarDerivationError as e:
            bad.append(f"⑩{term_key}: 推導失敗：{e}")
            continue
        got = [[w.number, w.start] for w in term.weeks]
        if got != [list(x) for x in expected["weeks"]]:
            first_diff = next((f"第 {g[0]} 週 {g[1]} ≠ {e2[1]}"
                               for g, e2 in zip(got, expected["weeks"]) if list(g) != list(e2)),
                              f"週數 {len(got)} ≠ {len(expected['weeks'])}")
            bad.append(f"⑩{term_key}: 週次表與校方公告不符（{first_diff}）")
    return bad


def build_term_calendar(
    events: Sequence[CalendarEvent], term_key: str, source_url: str, content_sha256: str,
    sibling: Optional[Tuple[str, AcademicTerm]] = None,
) -> TermCalendarFile:
    """推導 + 跑不變量。任一不過 → 拋錯，由呼叫端擋在上傳之前（publish.py 的 pre-flight）。"""
    term = derive_term(events, term_key)
    violations = check_invariants(term_key, term, sibling)
    if violations:
        raise CalendarDerivationError(
            f"{term_key} 週次表不變量未通過（保留上一版、不發布）:\n  " + "\n  ".join(violations))
    return TermCalendarFile(
        source=TermCalendarSource(
            url=source_url, content_sha256=content_sha256,
            parsed_at=dt.datetime.now(TAIPEI).isoformat(timespec="seconds"),
            parser_version=PARSER_VERSION,
            derived_fields=list(DERIVED_FIELDS),
        ),
        terms={term_key: term},
    )


def current_academic_year(today: Optional[dt.date] = None) -> int:
    """今天所在的學年度（民國）。學年度 Y 的區間是 Y-08 ~ (Y+1)-07。"""
    today = today or dt.datetime.now(TAIPEI).date()
    return (today.year if today.month >= 8 else today.year - 1) - 1911


def default_terms(today: Optional[dt.date] = None) -> List[str]:
    """預設只產**當前學年度**的兩個學期。

    「只產有把握的學期」——舊學年度回填只是多冒險（108~110 的「開學」本來就有多筆命中、
    也沒有 PDF 可對），而 App 只用得到當前學期與下學期。
    """
    ay = current_academic_year(today)
    return [f"{ay}-1", f"{ay}-2"]


def build_all_term_calendars(
    events: Sequence[CalendarEvent], term_keys: Sequence[str],
    source_url: str, content_sha256: str,
) -> Dict[str, TermCalendarFile]:
    """推導指定學期 + 跑①~⑦（含跨學期的⑦）+ 跑⑩回歸。任一不過 → 拋錯，全部不寫。

    全有或全無：週次表是同一份來源、同一套規則推出來的，其中一個學期不對代表規則或
    來源有問題，這時把另一個學期照發只是把錯誤藏起來。
    """
    regression = verify_week_table_regression(events)
    if regression:
        raise CalendarDerivationError(
            "週次表回歸未通過（保留上一版、不發布）:\n  " + "\n  ".join(regression))
    terms: Dict[str, AcademicTerm] = {}
    for key in term_keys:
        try:
            terms[key] = derive_term(events, key)
        except TermNotPublishedYet as e:
            logger.info("跳過 %s：%s", key, e)      # 常態，不是錯誤
    if not terms:
        # **全部都還沒匯入也是常態**，每年 8 月必然發生一段時間：舊學年度已結束、
        # 新學年度的 ics 還沒進來。回空字典、不拋錯——canonical 與 CDN 上的舊週次表
        # 原封不動保留，事件 feed 照常更新。「哪個學期該有卻沒有」由
        # infra/calendar_coverage_check.py 負責盯，不是靠讓整條管線死掉來通知。
        logger.warning("要求的學期 %s 在 ics 裡全都沒有事件——保留既有週次表不動",
                       list(term_keys))
        return {}
    violations: List[str] = []
    for k, term in terms.items():
        sibling = next(((k2, t2) for k2, t2 in terms.items()
                        if k2 != k and k2.split("-")[0] == k.split("-")[0]), None)
        violations += check_invariants(k, term, sibling)
    if violations:
        raise CalendarDerivationError(
            "週次表不變量未通過（保留上一版、不發布）:\n  " + "\n  ".join(violations))
    now = dt.datetime.now(TAIPEI).isoformat(timespec="seconds")
    return {
        k: TermCalendarFile(
            source=TermCalendarSource(
                url=source_url, content_sha256=content_sha256, parsed_at=now,
                parser_version=PARSER_VERSION, derived_fields=list(DERIVED_FIELDS)),
            terms={k: term},
        )
        for k, term in terms.items()
    }


def load_term(out_dir: Path, term_key: str) -> Optional[AcademicTerm]:
    """讀該學期 canonical/{term}/calendar.json 的 AcademicTerm（契約三）。沒有就回 None。

    逐週進度的日期／錨點規則需要它（weeks[] 用來映射、midterm/final_exam 當錨點）；
    沒有週次表時那些規則自動跳過，marker 路徑照常運作（110-1～114-2 全是這種）。
    原本在 reprocess.py；reprocess-progress 刪除後 derive 仍需要，移到這裡。
    """
    p = out_dir / "canonical" / term_key / "calendar.json"
    if not p.exists():
        return None
    cal = TermCalendarFile.model_validate_json(p.read_text(encoding="utf-8"))
    return cal.terms.get(term_key)
