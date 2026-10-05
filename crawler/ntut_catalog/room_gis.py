"""課程系統教室 → 校園 GIS 房間的對應（derive 層，D23）。

**房間宇宙是課程系統的教室清單**（Croom -2），不是 GIS——GIS 連辦公室、實驗室、廁所都有。
這裡只負責「課程系統這間教室在 GIS 的哪裡」，對不到就老實標 `none`，原始簡稱 `raw` 永遠保留
（App 校園地圖規劃指出：教室字串與 GIS 房號之間的 join key 是最大風險）。

GIS 端讀 canonical `gis/gis-rooms.json`——`campus_gis` 資料集（D28）每天從校園資料平台
ntutbox-campus 的公開 CDN 鏡像進 data branch，`gis/source.json` 記它的 revision／sha256。
canonical 沒有（本機開發、資料集上線前）→ 退回套件內凍結的 `reference/gis-rooms.fallback.json`
（D23 時代的 vendored 快照，updateSequence 1044，教室內容與 1146 相同）並 warning。fallback 隨套件安裝
（package-data），所以 derive 在任何環境都跑得起來；它不再更新，只是保底。
房間鍵＝(building_id, class_number)——class_number 只在同一棟內唯一；**不用** sourceFeatureId
（gid 重新匯入就會變）。對應放在 derive：GIS 一更新，下一次 derive 自動重算。

規則（依序）：
  1. override：`reference/gis-room-overrides.json` 以簡稱原文為鍵，**只收 GIS 查得到的**
     （該 (building_id, class_number) 的 GIS 名稱含 `gis_name`——GIS 上的名稱，不必與課程系統同名，
     例：共同演講廳 → GB B07「視聽教室(255人)」）；驗證不過 → 忽略並 warning、走規則。
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

from models import GisSnapshotInfo, RoomGisRef, TermRoomBuilding

logger = logging.getLogger(__name__)

REFERENCE = Path(__file__).parent / "reference"
FALLBACK_PATH = REFERENCE / "gis-rooms.fallback.json"
# canonical 內 campus_gis 資料集的兩個檔（registry.py 的 writes 用同樣的路徑）
GIS_ROOMS_REL = "gis/gis-rooms.json"
GIS_SOURCE_REL = "gis/source.json"
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
    # building → {"name", "label", "order"}（label／order 是 ntutbox-campus 的清單名稱與固定排序，選填）
    building_meta: Dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_snapshot(cls, snap: dict, campus: Optional[dict] = None) -> "GisIndex":
        """`snap`＝gis-rooms.json；`campus`＝canonical `gis/source.json`（CDN 鏡像才有）。

        兩種 `source` 形狀都收：舊 vendored 快照帶 `campus_map_manifest_sha256`，CDN 版只有
        `description`＋`update_sequence`。"""
        src = snap.get("source") or {}
        campus = campus or {}
        idx = cls(source=GisSnapshotInfo(
            update_sequence=src.get("update_sequence"),
            campus_map_manifest_sha256=src.get("campus_map_manifest_sha256"),
            campus_revision=campus.get("revision"),
            campus_sha256=campus.get("sha256")))
        for b in snap.get("buildings", []):
            bid = b["building_id"]
            idx.buildings.add(bid)
            idx.floors[bid] = set(b.get("floor_ids") or [])
            order = b.get("order")
            idx.building_meta[bid] = {"name": b.get("name"), "label": b.get("label"),
                                      "order": order if isinstance(order, int) else None}
        for r in snap.get("rooms", []):
            key = (r["building_id"], r["class_number"])
            idx.rooms.setdefault(key, set()).add(r["floor_id"])
            idx.names.setdefault(key, set()).update(x for x in (r.get("name"), r.get("use")) if x)
        return idx


def load_gis_index(canonical: Optional[Path] = None, fallback: Path = FALLBACK_PATH) -> GisIndex:
    """canonical `gis/gis-rooms.json`（campus_gis 鏡像，D28）優先；沒有 → fallback＋warning。"""
    path = canonical / GIS_ROOMS_REL if canonical is not None else None
    if path is not None and path.exists():
        src_path = canonical / GIS_SOURCE_REL
        campus = json.loads(src_path.read_text(encoding="utf-8")) if src_path.exists() else None
        return GisIndex.from_snapshot(json.loads(path.read_text(encoding="utf-8")), campus)
    logger.warning("canonical 沒有 %s（campus_gis 尚未跑過？）——教室 GIS 對應改用凍結的 fallback %s",
                   GIS_ROOMS_REL, fallback.name)
    return GisIndex.from_snapshot(json.loads(fallback.read_text(encoding="utf-8")))


def dump_gis_rooms(snap: dict) -> str:
    """gis-rooms.json 的確定性序列化：一列一筆（仍是合法 JSON），git diff 看得出哪些房間變了。

    鍵排序、緊湊分隔——與 ntutbox-campus 發布的格式相同，上游沒改格式時寫出的位元組＝CDN 原檔。
    建物保留上游順序（已依 `order`、再依 id 排好），房間也保留上游順序。"""
    def line(x) -> str:
        return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def block(items) -> str:
        return "[\n" + ",\n".join(line(x) for x in items) + "\n]"

    return ('{"source":' + line(snap["source"]) + ',\n"buildings":' + block(snap["buildings"])
            + ',\n"rooms":' + block(snap["rooms"]) + "}\n")


def dump_gis_source(info: dict) -> str:
    """`gis/source.json`：鏡像的是哪一版（不帶時間，D13）。"""
    return json.dumps(info, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def building_entries(gis: GisIndex, building_ids) -> List[TermRoomBuilding]:
    """v1 rooms.json 的 `buildings`：給定建物的清單名稱與排序（label 缺 → name → id）。

    排序同 ntutbox-campus：有 order 的依 order，沒有的排後面，再依 id。不在 GIS 的 id 略過。"""
    out = []
    for bid in sorted(set(building_ids)):
        meta = gis.building_meta.get(bid)
        if meta is None:
            continue
        out.append(TermRoomBuilding(building_id=bid, label=meta.get("label") or meta.get("name") or bid,
                                    order=meta.get("order")))
    out.sort(key=lambda b: (b.order is None, b.order or 0, b.building_id))
    return out


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
