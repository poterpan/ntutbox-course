"""從本機 ntut-campus-map 抽出教室對應用的精簡 GIS 快照（D23）。

  python infra/gis/build_snapshot.py /path/to/ntut-campus-map [--out crawler/ntut_catalog/reference/gis-rooms.json]

GIS 資料只在本機的 ntut-campus-map（沒有 git remote；來源是學校公開的 GeoServer WFS），
CI 拿不到，所以把對應需要的欄位**vendored 進本 repo**：
  - buildings：building_id、name、aliases、floor_ids
  - rooms：只收 classNumber 非空者的 building_id、floor_id、class_number、name、use（**不含幾何**）
  - source：GeoServer `updateSequence`（取自 source-metadata.json `wfs.updateSequence`）＋
    campus-map `v1/manifest.json` 的 sha256——weekly 把它與線上值記進 run summary（只記錄，見 #120）。
房間鍵＝(building_id, class_number)；**不帶 sourceFeatureId**（gid 重新匯入就會變，不能當鍵）。

輸出確定性（排序、去重、不含本次執行時間），一列一筆，git diff 看得出哪些房間變了。
只用標準庫。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import List, Optional

RESOURCES = Path("Sources/NTUTCampusMapData/Resources/v1")
DEFAULT_OUT = (Path(__file__).resolve().parents[2]
               / "crawler" / "ntut_catalog" / "reference" / "gis-rooms.json")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_snapshot(campus_map: Path) -> dict:
    v1 = campus_map / RESOURCES
    meta = _load(v1 / "source-metadata.json")
    manifest_bytes = (v1 / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    update_sequence = (meta.get("wfs") or {}).get("updateSequence")
    if not isinstance(update_sequence, int):
        raise ValueError(f"source-metadata.json 沒有整數 wfs.updateSequence：{update_sequence!r}")

    buildings = sorted(
        ({"building_id": b["buildingId"], "name": b.get("name"),
          "aliases": sorted(set(b.get("nameAliases") or [])),
          "floor_ids": list(b.get("floorIds") or [])}
         for b in _load(v1 / "building-index.json")["buildings"]),
        key=lambda b: b["building_id"])
    seen = set()
    rooms = []
    for r in _load(v1 / "room-index.json")["rooms"]:
        cn = r.get("classNumber")
        if not cn:
            continue
        row = (r["buildingId"], r["floorId"], cn, r.get("name"), r.get("use"))
        if row in seen:
            continue
        seen.add(row)
        rooms.append(row)
    rooms.sort(key=lambda x: tuple("" if v is None else v for v in x))
    return {
        "source": {
            "description": "ntut-campus-map v1（本機、無 remote；來源為學校公開 GeoServer WFS）的精簡抽取，"
                           "由 infra/gis/build_snapshot.py 產生，勿手改",
            "capabilities_url": (meta.get("wfs") or {}).get("capabilitiesURL"),
            "update_sequence": update_sequence,
            "campus_map_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "campus_map_generated_at": manifest.get("generatedAt"),
        },
        "buildings": buildings,
        "rooms": [{"building_id": b, "floor_id": f, "class_number": cn, "name": n, "use": u}
                  for b, f, cn, n, u in rooms],
    }


def dump_snapshot(snap: dict) -> str:
    """一列一筆的 JSON（仍是合法 JSON）：diff 友善、位元組確定。"""
    def line(x) -> str:
        return json.dumps(x, ensure_ascii=False, separators=(",", ":"))

    def block(items) -> str:
        return "[\n" + ",\n".join(line(x) for x in items) + "\n]"

    return ('{"source":' + line(snap["source"]) + ',\n"buildings":' + block(snap["buildings"])
            + ',\n"rooms":' + block(snap["rooms"]) + "}\n")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("campus_map", type=Path, help="ntut-campus-map 目錄")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    snap = build_snapshot(args.campus_map)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(dump_snapshot(snap), encoding="utf-8")
    print(f"wrote {args.out}: {len(snap['buildings'])} buildings, {len(snap['rooms'])} rooms, "
          f"updateSequence={snap['source']['update_sequence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
