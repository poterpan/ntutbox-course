"""教室課表（空教室查找的資料源，D23；北科盒子 App 的空教室查找）。

  fetch：Croom -2 清單（1 請求，失敗＝整個資料集失敗）→ 每間教室 Croom -3 週課表（一間＝一個節點，
         失敗記 `{"room": code}`、跳過續跑，由 merge 從 HEAD 沿用該間）→ canonical `{term}/rooms.json`
  derive：canonical ＋ GIS 快照 → v1 `terms/{term}/rooms.json`（對應規則在 room_gis.py）

canonical 只記學校給的：code、簡稱原文、全名、容量、有排課的格子（課號排序）。依 code 排序、
不帶時間；一列一間教室（仍是合法 JSON），git diff 看得出哪間教室的課表變了。

語意：slot＝「有排課」，不是「被占用」；沒有 slot ≠ 保證空著（社團借用、補課、會議不在課表裡）。
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from models import Room, RoomDirectory, RoomSlot, TermRoom, TermRooms
from ntut_catalog.nodes import NodeTally
from ntut_catalog.parse_room import parse_room_grid, parse_room_list

logger = logging.getLogger(__name__)


def _term(term_key: str):
    y, s = term_key.split("-")
    return int(y), int(s)


def code_sort_key(code: str):
    """教室碼多為數字字串：數字依數值、其他依字串，排在數字之後。"""
    return (0, int(code), "") if code.isdigit() else (1, 0, code)


def crawl_rooms(client, term_key: str, tally: Optional[NodeTally] = None) -> RoomDirectory:
    tally = tally if tally is not None else NodeTally()
    year, sem = _term(term_key)
    rows, warnings = parse_room_list(client.croom("-2", year, sem))
    for w in warnings:
        logger.warning("[%s] %s", term_key, w)
    if not rows:
        # 上游改版仍回 200 → 0 間。fail loud，不讓空清單覆寫既有 canonical。
        raise ValueError(f"[{term_key}] Croom -2 解析出 0 間教室——疑似上游改版，中止以保留既有資料")
    rooms: Dict[str, Room] = {}
    for row in rows:
        if row.code in rooms:
            logger.warning("[%s] Croom -2 重複的教室碼 %s（%s），只取第一筆", term_key, row.code, row.raw)
            continue
        tally.attempt()
        try:
            grid = parse_room_grid(client.croom("-3", year, sem, row.code))
        except Exception as e:  # noqa: BLE001 — 一間失敗不拖垮整輪，交給 merge
            logger.warning("[%s] Croom -3 code=%s（%s）失敗：%s", term_key, row.code, row.raw, e)
            tally.fail(room=row.code)
            continue
        rooms[row.code] = Room(
            code=row.code, raw=row.raw, full_name=row.full_name, capacity=row.capacity,
            slots=[RoomSlot(day=d, period=p, offering_ids=ids) for d, p, ids in grid])
    return RoomDirectory(term_key=term_key,
                         rooms=sorted(rooms.values(), key=lambda r: code_sort_key(r.code)))


def dump_rooms(directory: RoomDirectory) -> str:
    """canonical 序列化：一列一間（合法 JSON、位元組確定）。merge 的節點沿用也用這支重寫。"""
    head = json.dumps(directory.model_dump(exclude={"rooms"}), ensure_ascii=False,
                      separators=(",", ":"))
    body = ",\n".join(r.model_dump_json() for r in directory.rooms)
    return head[:-1] + ',"rooms":[\n' + body + "\n]}\n"


def load_rooms(path: Path) -> RoomDirectory:
    return RoomDirectory.model_validate_json(path.read_text(encoding="utf-8"))


def write_rooms(directory: RoomDirectory, out_dir: Path) -> Path:
    d = out_dir / "canonical" / directory.term_key
    d.mkdir(parents=True, exist_ok=True)
    path = d / "rooms.json"
    path.write_text(dump_rooms(directory), encoding="utf-8")
    return path


def build_term_rooms(directory: RoomDirectory, gis, overrides) -> TermRooms:
    """canonical ＋ GIS 快照 → v1 TermRooms（確定性、不連網）。"""
    from ntut_catalog.room_gis import map_room

    warnings: List[str] = []
    rooms = []
    for r in directory.rooms:
        match, refs = map_room(r.raw, gis, overrides, warnings)
        rooms.append(TermRoom(**r.model_dump(), gis=refs, gis_match=match))
    for w in sorted(set(warnings)):
        logger.warning("[%s] rooms: %s", directory.term_key, w)
    return TermRooms(term_key=directory.term_key, gis_snapshot=gis.source, rooms=rooms)


def match_summary(term_rooms: TermRooms) -> Counter:
    return Counter(r.gis_match for r in term_rooms.rooms)
