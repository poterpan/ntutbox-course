"""GIS 快照（infra/gis/build_snapshot.py）與 weekly 的 updateSequence 記錄（pipeline_alert gis-drift，D23）。

gis-drift 只記錄、不開 issue：updateSequence 會因與教室無關的變動前進（issue #120）。"""
import hashlib
import json
import ssl
import urllib.error
from argparse import Namespace

import pytest

from infra.gis.build_snapshot import RESOURCES, build_snapshot, dump_snapshot, main
from infra.pipeline_alert import cmd_gis_drift, fetch_update_sequence, main as alert_main
from ntut_catalog.room_gis import GisIndex
from tests.test_pipeline_alert import FakeGh


# ============================================================ 快照產生

def _campus_map(tmp_path, update_sequence=1044):
    v1 = tmp_path / "campus-map" / RESOURCES
    v1.mkdir(parents=True)
    (v1 / "source-metadata.json").write_text(json.dumps(
        {"wfs": {"updateSequence": update_sequence, "capabilitiesURL": "https://example/caps"}}),
        encoding="utf-8")
    (v1 / "manifest.json").write_bytes(b'{"generatedAt": "2026-08-29T16:36:01+00:00"}')
    (v1 / "building-index.json").write_text(json.dumps({"schemaVersion": 1, "buildings": [
        {"buildingId": "CB", "name": "綜合科館", "nameAliases": ["綜合科館"], "floorIds": ["B1", "1F"],
         "hasOfficialFootprint": True},
        {"buildingId": "A1T", "name": "第一教學大樓", "nameAliases": ["第一教學大樓"], "floorIds": ["1F"]},
    ]}, ensure_ascii=False), encoding="utf-8")
    room = {"aliases": ["x"], "sourceFeatureId": "CB_B1.3", "use": "第二演講廳"}
    (v1 / "room-index.json").write_text(json.dumps({"rooms": [
        {**room, "buildingId": "CB", "floorId": "B1", "classNumber": "B19", "name": "第二演講廳"},
        {**room, "buildingId": "CB", "floorId": "B1", "classNumber": "B19", "name": "第二演講廳",
         "sourceFeatureId": "CB_B1.4"},                        # 同房間兩個多邊形 → 去重成一列
        {**room, "buildingId": "A1T", "floorId": "1F", "classNumber": None, "name": "走道"},
        {**room, "buildingId": "A1T", "floorId": "1F", "classNumber": "101", "name": "多元功能教室",
         "use": "多元功能教室"},
    ]}, ensure_ascii=False), encoding="utf-8")
    return tmp_path / "campus-map"


def test_build_snapshot_slim_and_keyed(tmp_path):
    cm = _campus_map(tmp_path)
    snap = build_snapshot(cm)
    manifest = (cm / RESOURCES / "manifest.json").read_bytes()
    assert snap["source"]["update_sequence"] == 1044
    assert snap["source"]["campus_map_manifest_sha256"] == hashlib.sha256(manifest).hexdigest()
    assert [b["building_id"] for b in snap["buildings"]] == ["A1T", "CB"]
    assert snap["buildings"][1] == {"building_id": "CB", "name": "綜合科館", "aliases": ["綜合科館"],
                                    "floor_ids": ["B1", "1F"]}
    assert snap["rooms"] == [    # classNumber 非空、去重、排序；不含 sourceFeatureId／aliases／幾何
        {"building_id": "A1T", "floor_id": "1F", "class_number": "101", "name": "多元功能教室",
         "use": "多元功能教室"},
        {"building_id": "CB", "floor_id": "B1", "class_number": "B19", "name": "第二演講廳",
         "use": "第二演講廳"},
    ]
    text = dump_snapshot(snap)
    assert json.loads(text) == snap and "sourceFeatureId" not in text
    idx = GisIndex.from_snapshot(json.loads(text))
    assert idx.rooms[("CB", "B19")] == {"B1"} and idx.source.update_sequence == 1044


def test_build_snapshot_cli_is_deterministic(tmp_path):
    cm = _campus_map(tmp_path)
    out = tmp_path / "gis-rooms.json"
    assert main([str(cm), "--out", str(out)]) == 0
    first = out.read_bytes()
    assert main([str(cm), "--out", str(out)]) == 0
    assert out.read_bytes() == first


def test_build_snapshot_requires_update_sequence(tmp_path):
    cm = _campus_map(tmp_path, update_sequence=None)
    with pytest.raises(ValueError, match="updateSequence"):
        build_snapshot(cm)


# ============================================================ 漂移檢查

CAPS = b'<?xml version="1.0"?><wfs:WFS_Capabilities version="2.0.0" updateSequence="1146" xmlns:wfs="x">'


class _Resp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.body


def test_fetch_update_sequence_parses_attribute():
    assert fetch_update_sequence(urlopen=lambda url, timeout, **kw: _Resp(CAPS)) == (1146, None)


def test_fetch_update_sequence_retries_once_without_verification_on_ssl_error():
    calls = []

    def urlopen(url, timeout, context=None):
        calls.append(context)
        if context is None:
            raise urllib.error.URLError(ssl.SSLCertVerificationError("unable to get local issuer"))
        assert context.verify_mode == ssl.CERT_NONE
        return _Resp(CAPS)

    seq, note = fetch_update_sequence(urlopen=urlopen)
    assert seq == 1146 and len(calls) == 2 and "不驗證" in note


def test_fetch_update_sequence_other_errors_propagate():
    def urlopen(url, timeout, context=None):
        raise urllib.error.URLError(TimeoutError("timed out"))

    with pytest.raises(urllib.error.URLError):
        fetch_update_sequence(urlopen=urlopen)


def _snapshot(tmp_path, seq=1044):
    p = tmp_path / "gis-rooms.json"
    p.write_text(json.dumps({"source": {"update_sequence": seq}, "buildings": [], "rooms": []}),
                 encoding="utf-8")
    return Namespace(snapshot=p)


@pytest.fixture
def summary(tmp_path, monkeypatch):
    p = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(p))
    return p


def test_drift_mismatch_is_logged_not_an_issue(tmp_path, summary, capsys):
    gh = FakeGh()
    assert cmd_gis_drift(_snapshot(tmp_path), gh, fetch=lambda: (1146, None)) == 0
    assert gh.calls == []                                     # 不碰 issue
    out = capsys.readouterr().out
    assert "::notice" in out and "1044" in out and "1146" in out and "#120" in out
    text = summary.read_text(encoding="utf-8")
    assert "| 1044 | 1146 | 不同" in text and "#120" in text


def test_drift_equal_is_logged(tmp_path, summary):
    assert cmd_gis_drift(_snapshot(tmp_path, seq=1146), None, fetch=lambda: (1146, None)) == 0
    assert "| 1146 | 1146 | 一致 |" in summary.read_text(encoding="utf-8")


def test_drift_tls_note_goes_to_log_and_summary(tmp_path, summary, capsys):
    cmd_gis_drift(_snapshot(tmp_path), None, fetch=lambda: (1044, "TLS 驗證失敗，不驗證重試一次"))
    assert "不驗證重試一次" in capsys.readouterr().out
    assert "不驗證重試一次" in summary.read_text(encoding="utf-8")


def test_drift_fetch_failure_is_warning(tmp_path, summary, capsys):
    def boom():
        raise TimeoutError("timed out")

    assert cmd_gis_drift(_snapshot(tmp_path), None, fetch=boom) == 0
    assert "::warning" in capsys.readouterr().out and not summary.exists()


def test_cli_gis_drift_never_calls_gh(tmp_path, monkeypatch):
    import infra.pipeline_alert as pa
    monkeypatch.setattr(pa, "fetch_update_sequence", lambda: (1146, None))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    gh = FakeGh()
    assert alert_main(["gis-drift", "--snapshot", str(_snapshot(tmp_path).snapshot)], gh=gh) == 0
    assert gh.calls == []
