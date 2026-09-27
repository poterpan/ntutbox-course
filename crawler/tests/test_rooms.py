"""教室課表（rooms 資料集，D23）：Croom 解析、爬取與節點失敗、merge 沿用、GIS 對應、derive／manifest。

fixtures 是 2026-09-27 抓的 115-1 真實頁面（公開課務資料，無個資）：
  croom_-2_115-1.html            教室清單（231 間）
  croom_-3_115-1_438.html        六教526(e)：週五 2–4 節同格兩門課（367018 大學部＋367019 研究所合開）
  croom_-3_115-1_141_empty.html  設計501：本學期沒有排課（整張空課表）
  croom_-3_error.html            參數錯誤頁（「網址格式錯誤或參數不完整」）
"""
import datetime as dt
import json
from collections import Counter
from pathlib import Path

import pytest

from models import Room, RoomDirectory, RoomSlot, TermRooms
from ntut_catalog import fetch_state as fs
from ntut_catalog import pipeline, registry
from ntut_catalog.artifacts import derive
from ntut_catalog.merge import merge_fetch_output
from ntut_catalog.nodes import NodeTally
from ntut_catalog.parse_room import parse_room_grid, parse_room_list
from ntut_catalog.room_gis import (GisIndex, load_gis_index, load_overrides, map_room,
                                   normalize_raw)
from ntut_catalog.rooms import build_term_rooms, crawl_rooms, dump_rooms, load_rooms
from ntut_catalog.artifacts import write_canonical
from tests._fakes import build_sample_result
from tests.test_merge import _entry, _stage
from tests.test_pipeline import Clock, _ctx

FIXTURES = Path(__file__).parent / "fixtures"
T = "115-1"
CHECKED = "2026-09-28T05:30:00+08:00"


def _fx(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


# ============================================================ 解析

def test_list_parser_real_page():
    rows, warnings = parse_room_list(_fx("croom_-2_115-1.html"))
    assert len(rows) == 231 and warnings == []
    by_code = {r.code: r for r in rows}
    assert by_code["438"].raw == "六教526(e)"
    assert by_code["438"].full_name == "第六教學大樓526室" and by_code["438"].capacity == 40
    assert by_code["505"].raw == "思源講堂" and by_code["505"].capacity is None   # 空白 → None
    assert by_code["493"].raw == "一教1F(e)"


def test_list_parser_locates_columns_by_header_text():
    html = """<table><tr><th>容量(座位數)<th>教室全名<th>教室簡稱<th>備註
    <tr><td>30<td>某教室全名<td><a href="Croom.jsp?format=-3&year=115&sem=1&code=77">某教101</a><td>x
    <tr><td>　<td>無連結教室<td>某教102<td>y</table>"""
    rows, warnings = parse_room_list(html)
    assert [(r.code, r.raw, r.full_name, r.capacity) for r in rows] == [("77", "某教101", "某教室全名", 30)]
    assert len(warnings) == 1 and "某教102" in warnings[0]      # 沒有 code= → 略過並警告，不編造


def test_list_parser_rejects_page_without_header():
    with pytest.raises(ValueError):
        parse_room_list(_fx("croom_-3_error.html"))


def test_grid_multi_offering_cell():
    grid = parse_room_grid(_fx("croom_-3_115-1_438.html"))
    cells = {(d, p): ids for d, p, ids in grid}
    assert cells[(5, "2")] == cells[(5, "3")] == cells[(5, "4")] == ["367018", "367019"]
    assert cells[(4, "1")] == ["367154"] and cells[(1, "2")] == ["360750"]
    assert (0, "1") not in cells                              # 空格不列
    order = ["1", "2", "3", "4", "N", "5", "6", "7", "8", "9", "A", "B", "C", "D"]
    keys = [(d, order.index(p)) for d, p, _ in grid]
    assert keys == sorted(keys)                               # (day, 節次順序) 排序


def test_grid_empty_room_is_valid():
    assert parse_room_grid(_fx("croom_-3_115-1_141_empty.html")) == []


def test_grid_error_page_raises():
    with pytest.raises(ValueError, match="表頭"):
        parse_room_grid(_fx("croom_-3_error.html"))


def test_grid_unreadable_cell_raises():
    html = """<table><tr><th>　<th>日<th>一<th>二<th>三<th>四<th>五<th>六
    <tr><td>第 1 節<td>　<td>借用中<td>　<td>　<td>　<td>　<td>　</table>"""
    with pytest.raises(ValueError, match="讀不出課號"):
        parse_room_grid(html)


def test_grid_course_name_parens_not_mistaken_for_offering():
    html = """<table><tr><th>　<th>日<th>一<th>二<th>三<th>四<th>五<th>六
    <tr><td>第 A 節<td>　<td>(360001) [3人]<BR><a>微積分(1)</a><BR>(12)<td>　<td>　<td>　<td>　<td>　</table>"""
    assert parse_room_grid(html) == [(1, "A", ["360001"])]


# ============================================================ 爬取

class RoomClient:
    """回放 fixtures：清單三間（438 有課、141 空、9 回錯誤頁或 raise）。"""

    LIST = """<table><tr><th>教室簡稱<th>教室全名<th>容量(座位數)
    <tr><td><a href="Croom.jsp?format=-3&year=115&sem=1&code=438">六教526(e)</a><td>第六教學大樓526室<td>40
    <tr><td><a href="Croom.jsp?format=-3&year=115&sem=1&code=141">設計501</a><td>工設設計教室<td>
    <tr><td><a href="Croom.jsp?format=-3&year=115&sem=1&code=9">一教301</a><td>第一教學大樓301室<td>55
    </table>"""

    def __init__(self, fail=(), list_html=None):
        self.fail = set(fail)
        self.list_html = self.LIST if list_html is None else list_html
        self.calls = []
        self.request_count = 0

    def croom(self, format, year, sem, code=None):
        self.calls.append((format, year, sem, code))
        if format == "-2":
            return self.list_html
        if code in self.fail:
            raise RuntimeError("request failed after 5 attempts: Croom.jsp")
        return {"438": _fx("croom_-3_115-1_438.html"),
                "141": _fx("croom_-3_115-1_141_empty.html")}.get(code, _fx("croom_-3_error.html"))

    def close(self):
        pass


def test_crawl_rooms_nodes_and_sorting():
    tally = NodeTally()
    d = crawl_rooms(RoomClient(), T, tally=tally)
    assert [r.code for r in d.rooms] == ["141", "438"]        # 依 code 數值排序
    assert tally.total == 3 and tally.failed == [{"room": "9"}]   # 錯誤頁＝失敗節點，不寫空課表
    empty = d.rooms[0]
    assert empty.slots == [] and empty.capacity is None and empty.full_name == "工設設計教室"
    r438 = d.rooms[1]
    assert RoomSlot(day=5, period="2", offering_ids=["367018", "367019"]) in r438.slots


def test_crawl_rooms_empty_list_fails_loud():
    with pytest.raises(ValueError, match="0 間"):
        crawl_rooms(RoomClient(list_html="<table><tr><th>教室簡稱<th>教室全名<th>容量(座位數)</table>"), T)


def test_dump_rooms_is_deterministic_json_one_room_per_line():
    d = crawl_rooms(RoomClient(), T)
    text = dump_rooms(d)
    assert text == dump_rooms(RoomDirectory.model_validate_json(text))
    assert json.loads(text)["term_key"] == T
    lines = text.splitlines()
    assert lines[0].endswith('"rooms":[') and lines[-1] == "]}" and len(lines) == 2 + len(d.rooms)
    assert "checked_at" not in text and "generated_at" not in text


def test_registry_rooms_dataset():
    ds = registry.DATASETS["rooms"]
    assert (ds.cadence, ds.terms) == ("weekly", "active")
    assert ds.writes == ("{term}/rooms.json",) and ds.content == ("{term}/rooms.json",)
    assert registry.committable("115-1/rooms.json")


def test_pipeline_rooms_reports_failed_nodes(tmp_path):
    out, stage = tmp_path / "data", tmp_path / "stage"
    ctx = _ctx(out, Clock(dt.datetime.fromisoformat(CHECKED)),
               client_factory=lambda: RoomClient(fail={"141"}))
    r = pipeline.run("manual", ["rooms"], [T], out, stage, ctx=ctx, current_term=lambda: T)
    (e,) = r.datasets
    assert e["ok"] and e["files"] == [f"{T}/rooms.json"]
    assert e["node_total"] == 3 and e["failed_nodes"] == [{"room": "141"}, {"room": "9"}]
    assert (stage / "canonical" / T / "rooms.json").is_file()


# ============================================================ merge：節點沿用（D16）

def _room(code, raw, slots=((1, "1", ("360001",)),), capacity=40):
    return Room(code=code, raw=raw, full_name=f"{raw}全名", capacity=capacity,
                slots=[RoomSlot(day=d, period=p, offering_ids=list(ids)) for d, p, ids in slots])


HEAD_ROOMS = [_room(str(c), f"六教{c}") for c in range(1, 41)]   # 40 間


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.delenv("PARTIAL_FAILURE_MAX_RATIO", raising=False)
    monkeypatch.delenv("QUALITY_MIN_RATIO", raising=False)
    d = tmp_path / "data"
    (d / "canonical" / T).mkdir(parents=True)
    (d / "canonical" / T / "rooms.json").write_text(
        dump_rooms(RoomDirectory(term_key=T, rooms=HEAD_ROOMS)), encoding="utf-8")
    return d


def _merge_rooms(tmp_path, data, rooms, failed, node_total=40):
    rel = f"{T}/rooms.json"
    stage = _stage(tmp_path, "stage-rooms", [_entry(
        "rooms", T, checked_at=CHECKED, files=[rel], failed_nodes=failed, node_total=node_total)],
        {rel: dump_rooms(RoomDirectory(term_key=T, rooms=rooms))}, cadence="weekly")
    return merge_fetch_output(stage, data)


def _head(data):
    return (data / "canonical" / T / "rooms.json").read_bytes()


def test_failed_room_carried_forward_byte_identical(tmp_path, data):
    before = _head(data)
    fresh = [r for r in HEAD_ROOMS if r.code != "7"]
    rep = _merge_rooms(tmp_path, data, fresh, [{"room": "7"}])
    assert _head(data) == before                              # 其他都沒變 → 逐位元組相同
    assert rep.partial == [{"name": "rooms", "term": T, "failed": 1, "node_total": 40,
                            "carried_forward": [{"room": "7"}], "missing": []}]
    assert rep.applied[0]["partial"] is True
    (a,) = rep.alerts
    assert a["level"] == "warning" and "room=7" in a["message"]
    assert fs.get(fs.load(fs.path_for(data / "canonical")), "rooms", T)["checked_at"] == CHECKED


def test_carried_room_keeps_head_version_while_others_update(tmp_path, data):
    fresh = [(_room(r.code, r.raw, slots=((2, "N", ("369999",)),)) if r.code == "3" else r)
             for r in HEAD_ROOMS if r.code != "7"]
    _merge_rooms(tmp_path, data, fresh, [{"room": "7"}])
    merged = {r.code: r for r in load_rooms(data / "canonical" / T / "rooms.json").rooms}
    assert merged["7"] == HEAD_ROOMS[6]                        # HEAD 版本原樣
    assert merged["3"].slots[0].offering_ids == ["369999"]     # 成功的照常更新
    assert list(merged) == sorted(merged, key=int)


def test_failed_room_missing_in_head_is_left_out(tmp_path, data):
    rep = _merge_rooms(tmp_path, data, HEAD_ROOMS, [{"room": "999"}], node_total=41)
    codes = [r.code for r in load_rooms(data / "canonical" / T / "rooms.json").rooms]
    assert "999" not in codes                                  # 不寫一間空課表
    assert rep.partial[0]["missing"] == [{"room": "999"}] and rep.partial[0]["carried_forward"] == []


def test_too_many_failed_rooms_drop_dataset_term(tmp_path, data):
    before = _head(data)
    failed = [{"room": str(c)} for c in range(1, 4)]           # 3/40 = 7.5% > 5%
    rep = _merge_rooms(tmp_path, data, HEAD_ROOMS[3:], failed)
    assert _head(data) == before and rep.applied == []
    assert rep.dropped[0]["name"] == "rooms" and "超過 5%" in rep.dropped[0]["reason"]


# ============================================================ GIS 對應

SNAP = {
    "source": {"update_sequence": 1044, "campus_map_manifest_sha256": "ab" * 32},
    "buildings": [
        {"building_id": "A6T", "name": "第六教學大樓", "aliases": [], "floor_ids": ["B4", "5F"]},
        {"building_id": "CB", "name": "綜合科館", "aliases": [], "floor_ids": ["B1", "1F", "4F"]},
        {"building_id": "CE", "name": "土木館", "aliases": [], "floor_ids": ["1F", "2F"]},
        {"building_id": "EL", "name": "億光大樓", "aliases": [], "floor_ids": ["4F"]},
        {"building_id": "HR", "name": "宏裕科技研究大樓", "aliases": [], "floor_ids": ["2F"]},
        {"building_id": "ME", "name": "分子科學工程館", "aliases": [], "floor_ids": ["B1"]},
        {"building_id": "AM", "name": "先鋒國際研發大樓", "aliases": [], "floor_ids": ["2F"]},
    ],
    "rooms": [
        {"building_id": "A6T", "floor_id": "5F", "class_number": "526", "name": "教室", "use": "教室"},
        {"building_id": "CB", "floor_id": "1F", "class_number": "110-1", "name": "實驗室", "use": None},
        {"building_id": "CB", "floor_id": "4F", "class_number": "417-2", "name": "思源講堂", "use": "思源講堂"},
        {"building_id": "CB", "floor_id": "B1", "class_number": "B19", "name": "第二演講廳", "use": "第二演講廳"},
        {"building_id": "EL", "floor_id": "4F", "class_number": "405", "name": "教室", "use": None},
        {"building_id": "HR", "floor_id": "2F", "class_number": "231", "name": "教室", "use": None},
        {"building_id": "ME", "floor_id": "B1", "class_number": "BR6", "name": "實驗室", "use": None},
        {"building_id": "AM", "floor_id": "2F", "class_number": "201", "name": "教室", "use": None},
        # 同一個 class_number 兩層各有一個多邊形 → gis 列兩筆
        {"building_id": "A6T", "floor_id": "B4", "class_number": "526", "name": "教室", "use": None},
    ],
}
OVR = {
    "思源講堂": {"raw": "思源講堂", "building_id": "CB", "class_number": "417-2", "gis_name": "思源講堂"},
    "綜二演講廳": {"raw": "綜二演講廳", "building_id": "CB", "class_number": "B19", "gis_name": "第二演講廳"},
    "壞掉的": {"raw": "壞掉的", "building_id": "CB", "class_number": "B19", "gis_name": "第九演講廳"},
}


@pytest.fixture
def gis():
    return GisIndex.from_snapshot(SNAP)


def _m(raw, gis, overrides=OVR, warnings=None):
    match, refs = map_room(raw, gis, overrides, warnings)
    return match, [(g.building_id, g.floor_id, g.class_number) for g in refs]


def test_normalize_raw():
    assert normalize_raw("先鋒201 (e)") == "先鋒201"
    assert normalize_raw("六教526(e)") == "六教526"
    assert normalize_raw("科研大樓231e") == "科研大樓231"


@pytest.mark.parametrize("raw, expected", [
    ("六教526(e)", ("rule", [("A6T", "5F", "526"), ("A6T", "B4", "526")])),   # 多個多邊形
    ("綜科110_1", ("rule", [("CB", "1F", "110-1")])),                          # _N → -N
    ("億光0405", ("rule", [("EL", "4F", "405")])),                             # 去前導零
    ("科研大樓231e", ("rule", [("HR", "2F", "231")])),                          # 最長前綴＋去尾 e
    ("分子BR6", ("rule", [("ME", "B1", "BR6")])),
    ("先鋒201 (e)", ("rule", [("AM", "2F", "201")])),
    ("土木1F_1", ("floor_only", [("CE", "1F", None)])),
    ("土木2F", ("floor_only", [("CE", "2F", None)])),
    ("土木5F_2", ("building_only", [("CE", None, None)])),                     # GIS 沒有這層
    ("科研哈佛講堂", ("building_only", [("HR", None, None)])),                  # 講堂名不在規則內
    ("六教999", ("building_only", [("A6T", None, None)])),                      # 房號 GIS 沒有
    ("紡織501A", ("none", [])),                                                # GIS 沒有這棟
    ("化學103", ("none", [])),                                                 # 前綴有、快照沒這棟
])
def test_rules(gis, raw, expected):
    assert _m(raw, gis) == expected


def test_override_verified_by_gis_name(gis):
    assert _m("思源講堂", gis) == ("override", [("CB", "4F", "417-2")])
    assert _m("綜二演講廳", gis) == ("override", [("CB", "B1", "B19")])


def test_override_failing_verification_falls_back_to_rules(gis):
    warnings = []
    assert _m("壞掉的", gis, warnings=warnings) == ("none", [])
    assert len(warnings) == 1 and "驗證不過" in warnings[0]


def test_vendored_snapshot_maps_real_115_1_list():
    """repo 內的快照＋overrides 對 115-1 真實清單：分布是 D23 記錄的基準（快照或規則改了要更新這裡）。"""
    rows, _ = parse_room_list(_fx("croom_-2_115-1.html"))
    gis, overrides = load_gis_index(), load_overrides()
    assert gis.source.update_sequence == 1044
    got = {r.raw: map_room(r.raw, gis, overrides)[0] for r in rows}
    assert Counter(got.values()) == {"rule": 216, "override": 3, "floor_only": 7,
                                     "building_only": 3, "none": 2}
    assert got["思源講堂"] == got["綜二演講廳"] == got["綜三演講廳"] == "override"
    assert got["紡織501A"] == got["紡織503"] == "none"
    assert {k for k, v in got.items() if v == "building_only"} == {
        "共同演講廳", "科研哈佛講堂", "科研大樓243e"}


# ============================================================ derive／manifest

def _canonical_with_rooms(tmp_path):
    d = tmp_path / "data"
    write_canonical(build_sample_result(T), d)
    c = d / "canonical" / T
    directory = crawl_rooms(RoomClient(), T)
    (c / "rooms.json").write_text(dump_rooms(directory), encoding="utf-8")
    state = fs.load(fs.path_for(d / "canonical"))
    fs.update(state, "rooms", T, "sha", CHECKED)
    fs.save(fs.path_for(d / "canonical"), state)
    return d


def test_derive_rooms_v1_and_manifest(tmp_path):
    d = _canonical_with_rooms(tmp_path)
    manifest = derive(d)
    path = d / "v1" / "terms" / T / "rooms.json"
    v1 = TermRooms.model_validate_json(path.read_text(encoding="utf-8"))
    assert v1.gis_snapshot.update_sequence == 1044
    by = {r.code: r for r in v1.rooms}
    assert by["438"].raw == "六教526(e)" and by["438"].gis_match == "rule"
    assert {g.class_number for g in by["438"].gis} == {"526"}
    assert by["141"].slots == [] and by["141"].raw == "設計501"
    entry = manifest.terms[T].rooms
    assert entry.url == f"terms/{T}/rooms.json" and entry.size == path.stat().st_size
    assert entry.checked_at == CHECKED and entry.changed_at == CHECKED
    raw = json.loads((d / "v1" / "manifest.json").read_text(encoding="utf-8"))
    assert raw["terms"][T]["rooms"]["sha256"] == entry.sha256


def test_derive_rooms_is_deterministic(tmp_path):
    d = _canonical_with_rooms(tmp_path)
    derive(d)
    first = {p: p.read_bytes() for p in (d / "v1").rglob("*.json")}
    derive(d)
    second = {p: p.read_bytes() for p in (d / "v1").rglob("*.json")}
    assert first == second


def test_derive_without_rooms_has_no_manifest_entry(tmp_path):
    d = _canonical_with_rooms(tmp_path)
    (d / "canonical" / T / "rooms.json").unlink()
    assert derive(d).terms[T].rooms is None
