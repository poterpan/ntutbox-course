"""逐時段教室（D24）：rooms.json 反查 → v1 `meetings[].classroom_codes`＋一致性報告。"""
import json

import pytest

from models import CourseOffering, RoomDirectory
from ntut_catalog import meeting_rooms
from ntut_catalog.artifacts import derive, write_canonical
from ntut_catalog.rooms import dump_rooms
from tests.test_rooms import _room

T = "115-1"


def _course(oid, meetings, rooms=()):
    return CourseOffering.model_validate({
        "term_key": T, "offering_id": oid, "name": {"zh": f"課{oid}"},
        "classrooms": [{"code": c, "name": f"教室{c}"} for c in rooms],
        "meetings": [{"day": d, "periods": list(ps)} for d, ps in meetings],
        "selection": {"cwish_subj": oid},
    })


# 教室課表：
#   101：M（多教室課）週四 5,6；S（單教室）週一 1,2；P（partial）週二 3；C（conflict）週三 1；X（split）週五 5
#   102：M 週五 7；X 週五 6
ROOMS = RoomDirectory(term_key=T, rooms=[
    _room("101", "六教526", slots=((4, "5", ("M",)), (4, "6", ("M",)), (1, "1", ("S",)),
                                   (1, "2", ("S",)), (2, "3", ("P",)), (3, "1", ("C",)),
                                   (5, "5", ("X",)))),
    _room("102", "六教626", slots=((5, "7", ("M",)), (5, "6", ("X",)))),
])


def _courses():
    return [
        _course("M", [(4, "56"), (5, "7")], rooms=("101", "102")),   # 多教室、full
        _course("S", [(1, "12")], rooms=("101",)),                     # 單教室、full
        _course("N", [(2, "12")], rooms=()),                           # 無教室 → missing
        _course("P", [(2, "34")], rooms=("101",)),                     # 週二 4 查不到 → partial
        _course("C", [(3, "1")], rooms=("999",)),                      # 課程層級寫 999 → conflict
        _course("X", [(5, "56")], rooms=("101", "102")),               # 同一時段兩節不同教室 → split
        _course("Z", [], rooms=("101",)),                              # 沒有時段 → 不計
    ]


def test_attach_fills_per_meeting_codes_and_counts():
    courses = _courses()
    report = meeting_rooms.attach_meeting_rooms(courses, ROOMS)
    by = {c.offering_id: [m.classroom_codes for m in c.meetings] for c in courses}
    assert by["M"] == [["101"], ["102"]]
    assert by["S"] == [["101"]]
    assert by["N"] == [[]]
    assert by["P"] == [["101"]]
    assert by["C"] == [["101"]]
    assert by["X"] == [["101", "102"]]          # 聯集、依 code 排序
    assert report == {
        "courses_with_meetings": 6,
        "full": 4, "partial": 1, "missing": 1, "split": 1, "conflict": 1,
        "list_cap": meeting_rooms.LIST_CAP,
        "partial_ids": ["P"], "conflict_ids": ["C"],
    }


def test_multiple_rooms_in_one_slot_is_not_split():
    """同一節兩間教室（合班）不算 split——split 是「各節對到的教室不一樣」。"""
    rooms = RoomDirectory(term_key=T, rooms=[
        _room("101", "a", slots=((1, "1", ("A",)), (1, "2", ("A",)))),
        _room("102", "b", slots=((1, "1", ("A",)), (1, "2", ("A",)))),
    ])
    courses = [_course("A", [(1, "12")], rooms=("101", "102"))]
    report = meeting_rooms.attach_meeting_rooms(courses, rooms)
    assert courses[0].meetings[0].classroom_codes == ["101", "102"]
    assert report["split"] == 0 and report["full"] == 1 and report["conflict"] == 0


def test_list_cap(monkeypatch):
    monkeypatch.setattr(meeting_rooms, "LIST_CAP", 2)
    rooms = RoomDirectory(term_key=T, rooms=[
        _room("101", "a", slots=tuple((1, "1", (f"C{i}",)) for i in range(5)))])
    courses = [_course(f"C{i}", [(1, "1")], rooms=("999",)) for i in range(5)]
    report = meeting_rooms.attach_meeting_rooms(courses, rooms)
    assert report["conflict"] == 5 and report["conflict_ids"] == ["C0", "C1"]
    assert "…" in meeting_rooms.conflict_alert(T, report)["message"]


def test_report_only_rewritten_when_content_changes(tmp_path):
    rep = meeting_rooms.attach_meeting_rooms(_courses(), ROOMS)
    assert meeting_rooms.write_report(tmp_path, T, rep) is True
    path = meeting_rooms.report_path(tmp_path, T)
    before = path.stat().st_mtime_ns
    assert meeting_rooms.write_report(tmp_path, T, rep) is False
    assert path.stat().st_mtime_ns == before
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["term"] == T and "generated_at" not in body


# ------------------------------------------------------------------ derive 整合

@pytest.fixture
def canonical(tmp_path, sample_result):
    out = tmp_path / "data"
    sample_result.catalog.courses[:] = _courses()
    write_canonical(sample_result, out)
    return out


def _v1_meetings(out):
    cat = json.loads((out / "v1" / "terms" / T / "catalog.json").read_text(encoding="utf-8"))
    return {c["offering_id"]: [m["classroom_codes"] for m in c["meetings"]] for c in cat["courses"]}


def test_derive_without_rooms_leaves_codes_empty(canonical):
    derive(canonical)
    assert _v1_meetings(canonical)["M"] == [[], []]
    assert not meeting_rooms.report_path(canonical, T).exists()


def test_derive_fills_v1_only_and_is_deterministic(canonical):
    nd = canonical / "canonical" / T / "catalog.ndjson"
    (canonical / "canonical" / T / "rooms.json").write_text(dump_rooms(ROOMS), encoding="utf-8")
    before = nd.read_bytes()
    alerts: list = []
    derive(canonical, alerts=alerts)
    first = (canonical / "v1" / "terms" / T / "catalog.json").read_bytes()
    assert _v1_meetings(canonical)["M"] == [["101"], ["102"]]
    assert nd.read_bytes() == before                         # canonical 不動
    # conflict＋報告新產生 → 告警（測試沒有 canonical gis/，另有 campus_gis fallback 告警，D28）
    assert [a["name"] for a in alerts if a["name"] != "campus_gis"] == ["meeting-rooms"]
    mr = next(a for a in alerts if a["name"] == "meeting-rooms")
    assert mr["level"] == "warning" and "C" in mr["message"]
    again: list = []
    derive(canonical, alerts=again)
    assert (canonical / "v1" / "terms" / T / "catalog.json").read_bytes() == first
    assert [a for a in again if a["name"] != "campus_gis"] == []  # 報告沒變 → 不重複告警


def test_cli_derive_writes_alerts_file(canonical, tmp_path, capsys):
    from ntut_catalog import cli
    (canonical / "canonical" / T / "rooms.json").write_text(dump_rooms(ROOMS), encoding="utf-8")
    out = tmp_path / "derive-reports" / "derive-report.json"
    assert cli.main(["derive", "--out", str(canonical), "--alerts", str(out)]) == 0
    names = [a["name"] for a in json.loads(out.read_text(encoding="utf-8"))["alerts"]]
    assert [n for n in names if n != "campus_gis"] == ["meeting-rooms"]  # campus_gis：fallback 告警（D28）
    assert "::warning title=derive 警告 meeting-rooms" in capsys.readouterr().out
