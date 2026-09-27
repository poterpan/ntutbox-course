"""逐時段教室（D24）：用 Croom 教室課表反查每個上課時段在哪間教室。

課程系統的課程列只給「課程層級」的教室清單（一門課兩間教室時看不出哪個時段在哪間），
但 canonical `{term}/rooms.json` 是每間教室的週課表（教室 × 星期 × 節次 → 課號）。
反過來建索引 (課號, 星期, 節次) → 教室碼，就能填 v1 catalog 的 `meetings[].classroom_codes`。

- 只在 derive 做（canonical catalog 不動）；確定性、不連網。
- 該學期沒有 rooms.json → 不填（維持空 list，與之前相同）。
- 一個時段的各節對到不同教室 → 仍取聯集（報告記為 `split`）。
- 一致性報告 `canonical/reports/{term}/meeting-rooms.json`（不帶時間；內容沒變就不重寫）。
  `conflict`（課程層級教室集合 ≠ 反查到的集合）> 0 且報告內容有變 → warning 等級告警。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from models import CourseOffering, RoomDirectory
from ntut_catalog.rooms import code_sort_key

# 報告裡 partial／conflict 課號清單的上限（數字仍是全量）
LIST_CAP = 50

SlotIndex = Dict[Tuple[str, int, str], Set[str]]


def slot_index(directory: RoomDirectory) -> SlotIndex:
    """(課號, 星期, 節次) → 教室碼集合。"""
    idx: SlotIndex = defaultdict(set)
    for room in directory.rooms:
        for s in room.slots:
            for oid in s.offering_ids:
                idx[(oid, s.day, s.period)].add(room.code)
    return idx


def _sorted_codes(codes) -> List[str]:
    return sorted(codes, key=code_sort_key)


def attach_meeting_rooms(courses: List[CourseOffering], directory: RoomDirectory) -> dict:
    """就地填 `meetings[].classroom_codes`，回傳一致性報告（dict，不含學期以外的中繼資料）。

    每門有上課時段的課歸入 full／partial／missing 其一：
      full     每一節都反查得到教室
      partial  有的節查得到、有的查不到
      missing  全部查不到（該課不在任何教室的課表上，多為無教室的課）
    另計（可與上面重疊）：
      split    至少一個時段內，各節對到的教室不一樣（例：5 節在 A、6 節在 B）
      conflict 反查到的教室集合 ≠ 課程層級 `classrooms` 的教室碼集合（只在反查到東西時比）
    """
    idx = slot_index(directory)
    counts = {"full": 0, "partial": 0, "missing": 0, "split": 0, "conflict": 0}
    partial_ids: List[str] = []
    conflict_ids: List[str] = []
    total = 0
    for c in courses:
        if not c.meetings:
            continue
        total += 1
        hit = miss = 0
        split = False
        derived: Set[str] = set()
        for m in c.meetings:
            union: Set[str] = set()
            per_period: List[frozenset] = []
            for p in m.periods:
                rooms = idx.get((c.offering_id, m.day, p))
                if rooms:
                    hit += 1
                    union |= rooms
                    per_period.append(frozenset(rooms))
                else:
                    miss += 1
            if len(set(per_period)) > 1:
                split = True
            m.classroom_codes = _sorted_codes(union)
            derived |= union
        if hit and not miss:
            counts["full"] += 1
        elif hit:
            counts["partial"] += 1
            partial_ids.append(c.offering_id)
        else:
            counts["missing"] += 1
        if split:
            counts["split"] += 1
        course_level = {r.code for r in c.classrooms if r.code}
        if derived and derived != course_level:
            counts["conflict"] += 1
            conflict_ids.append(c.offering_id)
    return {
        "courses_with_meetings": total,
        **counts,
        "list_cap": LIST_CAP,
        "partial_ids": sorted(partial_ids)[:LIST_CAP],
        "conflict_ids": sorted(conflict_ids)[:LIST_CAP],
    }


def report_path(out_dir: Path, term: str) -> Path:
    return out_dir / "canonical" / "reports" / term / "meeting-rooms.json"


def write_report(out_dir: Path, term: str, report: dict) -> bool:
    """寫報告；內容（位元組）與既有相同就不重寫。回傳有沒有改變。"""
    path = report_path(out_dir, term)
    text = json.dumps({"term": term, **report}, ensure_ascii=False, indent=1) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def conflict_alert(term: str, report: dict) -> Optional[dict]:
    """conflict > 0 → warning 等級告警（格式同 merge 報告的 alerts，交給 pipeline_alert）。"""
    n = report.get("conflict", 0)
    if not n:
        return None
    ids = report.get("conflict_ids", [])
    more = "…" if n > len(ids) else ""
    return {
        "level": "warning",
        "name": "meeting-rooms",
        "term": term,
        "message": (f"{n} 門課的課程層級教室與 Croom 教室課表反查結果不一致"
                    f"（{'、'.join(ids)}{more}）；見 reports/{term}/meeting-rooms.json"),
    }
