"""season 排程（issue #111）：週次表的 `enrollment_windows` → 明確、整點對齊的觸發時刻表。

  data/ops/season-schedule.json   derive 產出（v1 之外）→ R2 `course/ops/season-schedule.json`

**邏輯全在這裡，Worker 只負責觸發**（D18）：Cloudflare Worker 的 Cron 每小時醒來，讀這份檔，
「現在這個整點」在 `slots` 裡 → 以 `terms` dispatch `season.yml`；不在 → 什麼都不做。
窗口解析只有一份（`term_calendar.derive_enrollment_windows`，寫進 `{term}/calendar.json`），
這裡只展開、不重新解析行事曆。

頻率規則（2026-09-27 定案，見 issue #111）：
  開啟後 BURST_HOURS 小時   每小時（open-burst）
  截止前 BURST_HOURS 小時   每小時（close-burst）
  截止時刻                  補一次（close；日間部 17:00、進修部 21:00——取窗口實際的截止時刻）
  其餘                      每 BASE_INTERVAL_HOURS 小時，台北時間 00／03／06… 對齊（base）
同一整點落在多個窗口／學期 → 合併成一格：`terms` 逗號串接（排序）、`windows` 聯集、
`reason` 取最具體者（close > close-burst > open-burst > base）。

**確定性**：範圍＝derive manifest `calendars` 那個窗口（最新學年度＋前一學年度，已有週次表者），
不讀系統時間——同一份 canonical → 逐位元組相同的輸出。過去的時刻照樣列出，Worker 只比對現在。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from models import AcademicTerm
from ntut_catalog.ics import TAIPEI
from ntut_catalog.term_calendar import load_term

SCHEDULE_SCHEMA_VERSION = 1
SCHEDULE_REL = "ops/season-schedule.json"      # 相對資料根目錄（data/）

# 頻率參數（issue #111 的三個設定值）
BURST_HOURS = 24              # 開啟後／截止前的高頻時長
BASE_INTERVAL_HOURS = 3       # 其餘時段的基本間隔（台北 00 點起對齊）
CLOSE_EXTRA_SLOT = True       # 截止時刻補跑一次

# 輸出的窗口顯示名（不照抄校方用語：「網路選課」其實是預選，容易誤會）
WINDOW_LABELS = {
    "preselection": "預選",                  # 校方行事曆稱「網路選課」
    "freshman_preselection": "新生預選",
    "post_start_add_drop": "開學後加退選",    # 校方稱「加選及無紀錄退選」
    "midterm_withdrawal": "期中撤選",
}
_LABEL_ORDER = list(WINDOW_LABELS.values())
# 越後面越具體
REASONS = ("base", "open-burst", "close-burst", "close")

Slot = Tuple[dt.datetime, str]      # (整點, reason)


def _ceil_hour(t: dt.datetime) -> dt.datetime:
    floor = t.replace(minute=0, second=0, microsecond=0)
    return floor if floor == t else floor + dt.timedelta(hours=1)


def window_slots(start: dt.datetime, end: dt.datetime) -> List[Slot]:
    """單一窗口 → [(整點, reason)]（時間遞增）。窗口內的整點依頻率規則取捨，截止時刻補一格。"""
    start, end = start.astimezone(TAIPEI), end.astimezone(TAIPEI)
    burst = dt.timedelta(hours=BURST_HOURS)
    out: List[Slot] = []
    t = _ceil_hour(start)
    while t < end:
        if t >= end - burst:
            out.append((t, "close-burst"))
        elif t < start + burst:
            out.append((t, "open-burst"))
        elif t.hour % BASE_INTERVAL_HOURS == 0:
            out.append((t, "base"))
        t += dt.timedelta(hours=1)
    if CLOSE_EXTRA_SLOT:
        out.append((_ceil_hour(end), "close"))
    return out


def build_schedule(terms: Dict[str, AcademicTerm],
                   calendar_sha256: Optional[str]) -> dict:
    """{所在學期: AcademicTerm} → season-schedule.json 的內容（dict）。slot 的 `terms` 是窗口的
    `target_term`，不是所在學期；被選學期有沒有自己的週次表都不影響（116-1 預選在 115-2 的檔裡）。"""
    merged: Dict[dt.datetime, dict] = {}
    for _host, term in sorted(terms.items()):
        for w in term.enrollment_windows:
            label = WINDOW_LABELS[w.kind]
            for at, reason in window_slots(dt.datetime.fromisoformat(w.start),
                                           dt.datetime.fromisoformat(w.end)):
                slot = merged.setdefault(at, {"terms": set(), "windows": set(), "reason": reason})
                # 刷的是**被選的學期**：115-1 期末的預選刷 115-2
                slot["terms"].add(w.target_term)
                slot["windows"].add(label)
                if REASONS.index(reason) > REASONS.index(slot["reason"]):
                    slot["reason"] = reason
    slots = [{"at": at.isoformat(timespec="seconds"),
              "terms": ",".join(sorted(v["terms"])),
              "windows": sorted(v["windows"], key=_LABEL_ORDER.index),
              "reason": v["reason"]}
             for at, v in sorted(merged.items())]
    return {"schema_version": SCHEDULE_SCHEMA_VERSION, "calendar_sha256": calendar_sha256,
            "slots": slots}


def _events_sha256(out_dir: Path) -> Optional[str]:
    nd = out_dir / "canonical" / "calendar" / "events.ndjson"
    return hashlib.sha256(nd.read_bytes()).hexdigest() if nd.exists() else None


def write_season_schedule(out_dir: Path, scope: Iterable[str]) -> Path:
    """derive 呼叫：scope（manifest `calendars` 的學期）→ `{out_dir}/ops/season-schedule.json`。

    每次都整份重寫（純衍生物）；沒有窗口也寫出空的 `slots`，Worker 看到的就是「不觸發」。
    """
    terms = {}
    for key in sorted(scope):
        term = load_term(out_dir, key)
        if term is not None:
            terms[key] = term
    data = build_schedule(terms, _events_sha256(out_dir))
    path = out_dir / SCHEDULE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8")
    return path


def load_schedule(out_dir: Path) -> Optional[dict]:
    path = out_dir / SCHEDULE_REL
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def summarize(terms: Dict[str, AcademicTerm]) -> Dict[Tuple[str, str], dict]:
    """(被選學期, 窗口名) → {count, first, last}：該窗口（日夜合併）自己的觸發格數（報告與測試用）。"""
    out: Dict[Tuple[str, str], dict] = {}
    by_key: Dict[Tuple[str, str], set] = {}
    for _host, term in sorted(terms.items()):
        for w in term.enrollment_windows:
            by_key.setdefault((w.target_term, WINDOW_LABELS[w.kind]), set()).update(
                at for at, _ in window_slots(dt.datetime.fromisoformat(w.start),
                                             dt.datetime.fromisoformat(w.end)))
    for key, ats in sorted(by_key.items()):
        ordered = sorted(ats)
        out[key] = {"count": len(ordered),
                    "first": ordered[0].isoformat(timespec="seconds"),
                    "last": ordered[-1].isoformat(timespec="seconds")}
    return out
