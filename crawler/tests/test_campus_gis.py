"""campus_gis 資料集（D28）：ntutbox-campus CDN 的 gis-rooms.json 鏡像 → canonical `gis/`，
derive 優先讀它、沒有才退回凍結的 fallback，並把大樓清單名稱／排序寫進 v1 rooms.json。不連網。"""
import json
import re
from pathlib import Path

import pytest

from models import TermRooms
from ntut_catalog import campus_cdn_client, pipeline, registry
from ntut_catalog.artifacts import derive
from ntut_catalog.merge import merge_fetch_output
from ntut_catalog.room_gis import (FALLBACK_PATH, GIS_ROOMS_REL, GIS_SOURCE_REL, GisIndex,
                                   building_entries, dump_gis_rooms, load_gis_index)
from tests._fakes import FAKE_GIS_ROOMS, FakeCampusClient
from tests.test_pipeline import Clock
from tests.test_rooms import T, _canonical_with_rooms

NOW = Clock(__import__("datetime").datetime.fromisoformat("2026-10-06T04:00:00+08:00"))


def _ctx(out, client):
    return registry.FetchContext(out, campus_client_factory=lambda: client, now=NOW)


def _fetch(out, client):
    return registry.fetch_campus_gis(_ctx(out, client), None)


# ============================================================ fetcher

def test_registered_daily_global():
    ds = registry.DATASETS["campus_gis"]
    assert (ds.cadence, ds.terms) == ("daily", "none")
    assert ds.writes == ("gis/gis-rooms.json", "gis/source.json")
    assert ds.content == ("gis/gis-rooms.json",)
    assert registry.committable("gis/gis-rooms.json") and registry.committable("gis/source.json")


def test_fetch_writes_deterministic_files(tmp_path):
    client = FakeCampusClient()
    out = _fetch(tmp_path, client)
    assert out.files == [GIS_ROOMS_REL, GIS_SOURCE_REL]
    rooms = (tmp_path / "canonical" / GIS_ROOMS_REL).read_text(encoding="utf-8")
    assert json.loads(rooms) == FAKE_GIS_ROOMS
    assert rooms == dump_gis_rooms(FAKE_GIS_ROOMS)
    lines = rooms.splitlines()      # 一列一筆：source、"buildings":[、N 棟、],、"rooms":[、M 間、]}
    n_b, n_r = len(FAKE_GIS_ROOMS["buildings"]), len(FAKE_GIS_ROOMS["rooms"])
    assert lines[0].startswith('{"source":') and len(lines) == 1 + 1 + n_b + 1 + 1 + n_r + 1
    src = json.loads((tmp_path / "canonical" / GIS_SOURCE_REL).read_text(encoding="utf-8"))
    assert src == {"manifest": "manifest.0123456789ab.json", "revision": "r2",
                   "sha256": client.digest, "update_sequence": 1146}
    # 再抓一次（另一個 checkout）位元組相同
    other = tmp_path / "other"
    _fetch(other, FakeCampusClient())
    for rel in (GIS_ROOMS_REL, GIS_SOURCE_REL):
        assert (other / "canonical" / rel).read_bytes() == (tmp_path / "canonical" / rel).read_bytes()


def test_source_json_passes_redline(tmp_path):
    from infra.redline_scan import scan_text
    _fetch(tmp_path, FakeCampusClient(revision=123456789012))
    text = (tmp_path / "canonical" / GIS_SOURCE_REL).read_text(encoding="utf-8")
    assert '"r123456789012"' in text and scan_text(text) == []


def test_fetch_skips_when_manifest_unchanged(tmp_path):
    _fetch(tmp_path, FakeCampusClient())
    client = FakeCampusClient()
    out = _fetch(tmp_path, client)
    assert out.files == [] and client.requests == ["current.json"]     # 只讀 current.json


def test_new_manifest_same_content_only_rewrites_source(tmp_path):
    _fetch(tmp_path, FakeCampusClient())
    out = _fetch(tmp_path, FakeCampusClient(revision=3, manifest="manifest.ffffffffffff.json"))
    assert out.files == [GIS_SOURCE_REL]
    src = json.loads((tmp_path / "canonical" / GIS_SOURCE_REL).read_text(encoding="utf-8"))
    assert src["revision"] == "r3" and src["manifest"] == "manifest.ffffffffffff.json"


@pytest.mark.parametrize("kwargs, match", [
    ({"sha256": "0" * 64}, "sha256 不符"),
    ({"include_gis": False}, "沒有 gis-rooms.json"),
    ({"schema_version": 2}, "schema_version"),
    ({"manifest": "../evil.json"}, "manifest 名稱"),
    ({"gis_rooms": {"source": {}, "buildings": [], "rooms": []}}, "缺 source"),
])
def test_fetch_rejects_bad_upstream(tmp_path, kwargs, match):
    with pytest.raises(RuntimeError, match=match):
        _fetch(tmp_path, FakeCampusClient(**kwargs))
    assert not (tmp_path / "canonical" / "gis").exists()


def _gis_without(building=None, room_field=None):
    snap = json.loads(json.dumps(FAKE_GIS_ROOMS))
    if building:
        snap["buildings"] = [b for b in snap["buildings"] if b["building_id"] != building]
    if room_field:
        del snap["rooms"][0][room_field]
    return snap


@pytest.mark.parametrize("snap, match", [
    (_gis_without(room_field="floor_id"), "格式不符"),     # 上游欄位改名／缺漏：derive 會 KeyError
    (_gis_without(building="HR"), "缺少課表會用到的大樓"),  # 課表前綴表會用到的大樓不見了
])
def test_fetch_rejects_snapshot_derive_cannot_use(tmp_path, snap, match):
    """sha 對得上只代表檔案沒壞；內容 derive 用不了 → 不收，保留上一份、不卡住每天的發布。"""
    with pytest.raises(RuntimeError, match=match):
        _fetch(tmp_path, FakeCampusClient(gis_rooms=snap))
    assert not (tmp_path / "canonical" / "gis").exists()


def test_fetch_rejects_sharp_room_drop(tmp_path):
    _fetch(tmp_path, FakeCampusClient())  # 上一份：3 間
    shrunk = json.loads(json.dumps(FAKE_GIS_ROOMS))
    shrunk["rooms"] = shrunk["rooms"][:1]
    with pytest.raises(RuntimeError, match="教室數驟降"):
        _fetch(tmp_path, FakeCampusClient(revision=3, manifest="manifest.eeeeeeeeeeee.json", gis_rooms=shrunk))


def test_derive_with_fallback_raises_alert(tmp_path):
    d = _canonical_with_rooms(tmp_path)
    alerts = []
    derive(d, alerts=alerts)
    assert [a["name"] for a in alerts] == ["campus_gis"]


def test_failed_fetch_keeps_last_good_copy(tmp_path):
    """sha 不符 → pipeline 記失敗 → merge 丟棄，data branch 保留上一份。"""
    data = tmp_path / "data"
    _fetch(data, FakeCampusClient())
    good = (data / "canonical" / GIS_ROOMS_REL).read_bytes()
    checkout, stage = tmp_path / "checkout", tmp_path / "stage"
    bad = FakeCampusClient(revision=3, manifest="manifest.ffffffffffff.json", sha256="0" * 64)
    result = pipeline.run("daily", ["campus_gis"], [], checkout, stage, ctx=_ctx(checkout, bad),
                          current_term=lambda: T)
    assert not result.ok and "sha256" in result.datasets[0]["error"]
    report = merge_fetch_output(stage, data)
    assert report.dropped and report.dropped[0]["name"] == "campus_gis"
    assert (data / "canonical" / GIS_ROOMS_REL).read_bytes() == good


def test_pipeline_merge_marks_changed_then_unchanged(tmp_path):
    data, stage = tmp_path / "data", tmp_path / "stage"
    pipeline.run("daily", ["campus_gis"], [], data, stage, ctx=_ctx(data, FakeCampusClient()),
                 current_term=lambda: T)
    report = merge_fetch_output(stage, tmp_path / "merged")
    assert report.applied == [{"name": "campus_gis", "term": None, "changed": True}]
    assert (tmp_path / "merged" / "canonical" / GIS_SOURCE_REL).exists()


def test_user_agent_passes_cdn_waf():
    assert not re.search(r"bot|crawl|spider", campus_cdn_client._UA, re.IGNORECASE)


# ============================================================ derive

def _write_canonical_gis(canonical: Path, snap=FAKE_GIS_ROOMS, revision="r2"):
    (canonical / "gis").mkdir(parents=True, exist_ok=True)
    (canonical / GIS_ROOMS_REL).write_text(dump_gis_rooms(snap), encoding="utf-8")
    (canonical / GIS_SOURCE_REL).write_text(json.dumps(
        {"manifest": "manifest.0123456789ab.json", "revision": revision, "sha256": "a" * 64,
         "update_sequence": 1146}), encoding="utf-8")


def test_load_gis_index_prefers_canonical(tmp_path):
    _write_canonical_gis(tmp_path)
    idx = load_gis_index(tmp_path)
    assert idx.source.update_sequence == 1146
    assert idx.source.campus_revision == "r2" and idx.source.campus_sha256 == "a" * 64
    assert idx.source.campus_map_manifest_sha256 is None
    assert idx.building_meta["HR"] == {"name": "宏裕科技研究大樓", "label": "宏裕科研大樓", "order": 70}


def test_load_gis_index_falls_back_with_warning(tmp_path, caplog):
    idx = load_gis_index(tmp_path)                    # canonical 沒有 gis/
    assert idx.source.update_sequence == 1044 and idx.source.campus_revision is None
    assert "fallback" in caplog.text
    assert load_gis_index().source.update_sequence == 1044
    assert FALLBACK_PATH.exists()


def test_building_entries_label_order_fallbacks():
    idx = GisIndex.from_snapshot(FAKE_GIS_ROOMS)
    got = building_entries(idx, ["CB", "RB", "HR", "A1T", "XX"])
    assert [(b.building_id, b.label, b.order) for b in got] == [
        ("A1T", "第一教學大樓", 10), ("HR", "宏裕科研大樓", 70), ("CB", "綜合科館", 90),
        ("RB", "紅樓", None)]                          # 沒有 label → name；沒有 order 排最後；XX 不在 GIS


def test_derive_uses_canonical_gis_and_emits_buildings(tmp_path):
    d = _canonical_with_rooms(tmp_path)
    snap = json.loads(FALLBACK_PATH.read_text(encoding="utf-8"))
    labels = {"A6T": ("第六教學大樓", 60), "HR": ("宏裕科研大樓", 70), "DB": ("設計館", 120)}
    for b in snap["buildings"]:
        if b["building_id"] in labels:
            b["label"], b["order"] = labels[b["building_id"]]
    snap["source"] = {"description": "x", "update_sequence": 1146}
    _write_canonical_gis(d / "canonical", snap)
    derive(d)
    v1 = TermRooms.model_validate_json(
        (d / "v1" / "terms" / T / "rooms.json").read_text(encoding="utf-8"))
    assert v1.gis_snapshot.update_sequence == 1146 and v1.gis_snapshot.campus_revision == "r2"
    used = {g.building_id for r in v1.rooms for g in r.gis}
    assert {b.building_id for b in v1.buildings} == used
    orders = [b.order for b in v1.buildings]
    with_order = [o for o in orders if o is not None]
    assert with_order == sorted(with_order) and orders[:len(with_order)] == with_order
    by = {b.building_id: b for b in v1.buildings}
    assert by["A6T"].label == "第六教學大樓" and by["A6T"].order == 60
    for bid, b in by.items():
        if bid not in labels:                         # 沒有 label → GIS 名稱
            assert b.order is None and b.label


def test_derive_without_canonical_gis_uses_fallback(tmp_path):
    d = _canonical_with_rooms(tmp_path)
    derive(d)
    v1 = TermRooms.model_validate_json(
        (d / "v1" / "terms" / T / "rooms.json").read_text(encoding="utf-8"))
    assert v1.gis_snapshot.update_sequence == 1044 and v1.buildings
    assert all(b.order is None for b in v1.buildings)
