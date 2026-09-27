"""課程系統教室 → 校園 GIS 房間的對應（derive 層，D23）。

**房間宇宙是課程系統的教室清單**（Croom -2），不是 GIS——GIS 連辦公室、實驗室、廁所都有。
這裡只負責「課程系統這間教室在 GIS 的哪裡」，對不到就老實標 `none`，原始簡稱 `raw` 永遠保留
（poterpan/NTUTBox#242「join key 是最大風險」）。

GIS 端用 repo 內的精簡快照 `reference/gis-rooms.json`（`infra/gis/build_snapshot.py` 從本機
ntut-campus-map 產生），房間鍵＝(building_id, class_number)——class_number 只在同一棟內唯一；
**不用** sourceFeatureId（gid 重新匯入就會變）。對應放在 derive：快照更新後下一次 derive 自動重算。

規則（依序）：
  1. override：`reference/gis-room-overrides.json` 以簡稱原文為鍵，**只收 GIS 名稱可驗證的**
     （該 (building_id, class_number) 的 GIS 名稱含 `gis_name`）；驗證不過 → 忽略並 warning、走規則。
  2. 棟別前綴表（最長前綴優先）：一教→A1T … 科研大樓／科研→HR。對不到前綴（如「紡織」，GIS 沒有這棟）→ none。
  3. 前綴後的部分先去掉空白、`(e)`、數字後的 `e`：
     - 樓層式（`1F`、`1F_1`、`B1F`）→ floor_only（該樓層存在於 GIS 才算，否則 building_only）
     - 房號式：`_N`→`-N`（綜科110_1 → 110-1），先試原樣、再試去前導零（億光0405 → 405）；
       GIS 有 → rule，沒有 → building_only
     - 其他文字（如「演講廳」「哈佛講堂」）→ building_only
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from models import GisSnapshotInfo, RoomGisRef

logger = logging.getLogger(__name__)

REFERENCE = Path(__file__).parent / "reference"
SNAPSHOT_PATH = REFERENCE / "gis-rooms.json"
OVERRIDES_PATH = REFERENCE / "gis-room-overrides.json"

# 課程系統教室簡稱的棟別前綴 → GIS buildingId。比對時最長前綴優先（「科研大樓」先於「科研」）。
# 2026-09-25 以 115-1 的 231 間試對：只靠這張表＋下面的正規化就有 216 間精確對到 GIS 房號。
BUILDING_PREFIXES: Dict[str, str] = {
    "一教": "A1T", "二教": "A2T", "三教": "A3T", "四教": "A4T", "五教": "A5T", "六教": "A6T",
    "綜科": "CB", "設計": "DB", "共同": "GB", "先鋒": "AM", "億光": "EL", "土木": "CE",
    "光華館": "GH", "分子": "ME", "化工": "CM", "國百館": "SY", "化學": "CH", "材資": "MR",
    "科研大樓": "HR", "科研": "HR",
}
_PREFIXES_LONGEST_FIRST = sorted(BUILDING_PREFIXES.items(), key=lambda kv: -len(kv[0]))

_ONLINE_SUFFIX_RE = re.compile(r"[\(（]e[\)）]$", re.IGNORECASE)
_TRAILING_E_RE = re.compile(r"(?<=\d)e$", re.IGNORECASE)
_FLOOR_RE = re.compile(r"^(B?)(\d+)F(?:_\d+)?$")
_ROOM_RE = re.compile(r"^[A-Z]*\d+[A-Z]?(?:_\d+)?$")


@dataclass
class GisIndex:
    """快照的查詢索引。"""
    source: GisSnapshotInfo = field(default_factory=GisSnapshotInfo)
    buildings: Set[str] = field(default_factory=set)
    floors: Dict[str, Set[str]] = field(default_factory=dict)                   # building → floors
    rooms: Dict[Tuple[str, str], Set[str]] = field(default_factory=dict)        # (b, cn) → floors
    names: Dict[Tuple[str, str], Set[str]] = field(default_factory=dict)        # (b, cn) → 名稱/用途

    @classmethod
    def from_snapshot(cls, snap: dict) -> "GisIndex":
        src = snap.get("source") or {}
        idx = cls(source=GisSnapshotInfo(
            update_sequence=src.get("update_sequence"),
            campus_map_manifest_sha256=src.get("campus_map_manifest_sha256")))
        for b in snap.get("buildings", []):
            idx.buildings.add(b["building_id"])
            idx.floors[b["building_id"]] = set(b.get("floor_ids") or [])
        for r in snap.get("rooms", []):
            key = (r["building_id"], r["class_number"])
            idx.rooms.setdefault(key, set()).add(r["floor_id"])
            idx.names.setdefault(key, set()).update(x for x in (r.get("name"), r.get("use")) if x)
        return idx


def load_gis_index(path: Path = SNAPSHOT_PATH) -> GisIndex:
    return GisIndex.from_snapshot(json.loads(path.read_text(encoding="utf-8")))


def load_overrides(path: Path = OVERRIDES_PATH) -> Dict[str, dict]:
    if not path.exists():
        return {}
    return {o["raw"]: o for o in json.loads(path.read_text(encoding="utf-8"))["overrides"]}


def normalize_raw(raw: str) -> str:
    """去空白、`(e)`、數字後的 `e`（「先鋒201 (e)」→「先鋒201」、「科研大樓231e」→「科研大樓231」）。"""
    n = re.sub(r"\s+", "", raw)
    n = _ONLINE_SUFFIX_RE.sub("", n)
    return _TRAILING_E_RE.sub("", n)


def _refs(gis: GisIndex, building: str, class_number: str) -> List[RoomGisRef]:
    return [RoomGisRef(building_id=building, floor_id=f, class_number=class_number)
            for f in sorted(gis.rooms[(building, class_number)])]


def _override(raw: str, gis: GisIndex, overrides: Dict[str, dict],
              warnings: List[str]) -> Optional[List[RoomGisRef]]:
    o = overrides.get(raw)
    if o is None:
        return None
    key = (o["building_id"], o["class_number"])
    names = gis.names.get(key)
    if names is None or not any(o["gis_name"] in n for n in names):
        warnings.append(f"override {raw!r} → {key} 在 GIS 快照驗證不過"
                        f"（GIS 名稱 {sorted(names) if names else '無此房間'}，期待含 {o['gis_name']!r}），改走規則")
        return None
    return _refs(gis, *key)


def map_room(raw: str, gis: GisIndex, overrides: Dict[str, dict],
             warnings: Optional[List[str]] = None) -> Tuple[str, List[RoomGisRef]]:
    """教室簡稱原文 → (gis_match, gis refs)。確定性、不連網。"""
    warnings = warnings if warnings is not None else []
    refs = _override(raw, gis, overrides, warnings)
    if refs is not None:
        return "override", refs
    n = normalize_raw(raw)
    hit = next(((p, b) for p, b in _PREFIXES_LONGEST_FIRST if n.startswith(p)), None)
    if hit is None or hit[1] not in gis.buildings:
        return "none", []
    prefix, building = hit
    rest = n[len(prefix):]
    m = _FLOOR_RE.match(rest)
    if m:
        floor = f"B{m.group(2)}" if m.group(1) else f"{int(m.group(2))}F"
        if floor in gis.floors.get(building, set()):
            return "floor_only", [RoomGisRef(building_id=building, floor_id=floor)]
        return "building_only", [RoomGisRef(building_id=building)]
    if _ROOM_RE.match(rest):
        dashed = re.sub(r"_(\d+)$", r"-\1", rest)
        for cand in (dashed, re.sub(r"^0+(?=\d)", "", dashed)):
            if (building, cand) in gis.rooms:
                return "rule", _refs(gis, building, cand)
    return "building_only", [RoomGisRef(building_id=building)]
