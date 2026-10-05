"""infra/web_redeploy.py：publish 後要不要觸發 web 重新部署（D22）。"""
import datetime as dt
import json

from infra.web_redeploy import (
    TAIPEI, changed_catalog_terms, changed_rooms_terms, decide, main, resolve_default_term,
    resolve_room_term,
)

NOW = dt.datetime(2026, 12, 1, 12, 0, tzinfo=TAIPEI)
SCHEDULE = {"term_schedule": {
    "current": [{"term": "115-1", "from": "2026-08-01T00:00:00+08:00"}],
    "default": [{"term": "115-1", "from": "2026-08-01T00:00:00+08:00"},
                {"term": "115-2", "from": "2026-11-21T17:00:00+08:00"}],
}}


def _reports(tmp_path, applied, name="merge-report-stage-daily.json"):
    d = tmp_path / "reports"
    d.mkdir(exist_ok=True)
    (d / name).write_text(json.dumps({"applied": applied}), encoding="utf-8")
    return d


def test_changed_catalog_terms_only_catalog_and_changed(tmp_path):
    d = _reports(tmp_path, [
        {"name": "catalog", "term": "115-1", "changed": True},
        {"name": "catalog", "term": "115-2", "changed": False},
        {"name": "details", "term": "115-2", "changed": True},
        {"name": "enrollment", "term": "115-1", "changed": True},
    ])
    _reports(tmp_path, [{"name": "catalog", "term": "114-2", "changed": True}], "merge-report-x.json")
    assert changed_catalog_terms(d) == {"115-1", "114-2"}
    assert changed_catalog_terms(tmp_path / "missing") == set()
    assert changed_catalog_terms(None) == set()


def test_resolve_default_term_latest_effective():
    assert resolve_default_term(SCHEDULE, NOW) == "115-2"
    before = dt.datetime(2026, 11, 21, 16, 59, tzinfo=TAIPEI)
    assert resolve_default_term(SCHEDULE, before) == "115-1"
    at = dt.datetime(2026, 11, 21, 9, 0, tzinfo=dt.timezone.utc)   # 同一 instant、不同時區寫法
    assert resolve_default_term(SCHEDULE, at) == "115-2"


def test_resolve_default_term_unresolvable():
    assert resolve_default_term(None, NOW) is None
    assert resolve_default_term({"terms": {}}, NOW) is None
    assert resolve_default_term({"term_schedule": {"default": "x"}}, NOW) is None
    future = {"term_schedule": {"default": [{"term": "116-1", "from": "2027-08-01T00:00:00+08:00"}]}}
    assert resolve_default_term(future, NOW) is None
    bad = {"term_schedule": {"default": [{"term": "115-2", "from": "nope"}, {"from": "2026-01-01T00:00:00+08:00"}]}}
    assert resolve_default_term(bad, NOW) is None


def test_resolve_default_term_falls_back_like_web_resolveTerms():
    """與 apps/web resolveTerms 同語意：預設學期沒有 catalog → 本學期 → terms 最新者（D21）。"""
    no_115_2 = {**SCHEDULE, "terms": {"114-2": {}, "115-1": {}}}
    assert resolve_default_term(no_115_2, NOW) == "115-1"          # hub 仍建 115-1
    assert decide({"115-1"}, resolve_default_term(no_115_2, NOW))[0] is True
    assert resolve_default_term({**SCHEDULE, "terms": {"115-1": {}, "115-2": {}}}, NOW) == "115-2"
    assert resolve_default_term({**SCHEDULE, "terms": {"114-1": {}, "114-2": {}}}, NOW) == "114-2"
    no_current = {"term_schedule": {"default": SCHEDULE["term_schedule"]["default"]},
                  "terms": {"115-1": {}}}                           # current 缺 → 日期規則
    assert resolve_default_term(no_current, NOW) == "115-1"


def test_decide():
    assert decide(set(), "115-2")[0] is False
    assert decide({"115-2"}, "115-2")[0] is True
    assert decide({"115-1"}, "115-2")[0] is False
    ok, reason = decide({"115-1"}, None)            # 解析不出預設學期 → 任一學期有變就部署
    assert ok and "115-1" in reason


def test_main_writes_github_output(tmp_path, monkeypatch, capsys):
    d = _reports(tmp_path, [{"name": "catalog", "term": "115-2", "changed": True}])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(SCHEDULE), encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert main(["--merge-reports", str(d), "--manifest", str(manifest), "--now", NOW.isoformat()]) == 0
    assert "redeploy=true" in out.read_text(encoding="utf-8")
    assert "115-2" in capsys.readouterr().out


def test_main_manifest_missing_falls_back_to_any_term(tmp_path, monkeypatch):
    d = _reports(tmp_path, [{"name": "catalog", "term": "114-2", "changed": True}])
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert main(["--merge-reports", str(d), "--manifest", str(tmp_path / "nope.json")]) == 0
    assert "redeploy=true" in out.read_text(encoding="utf-8")


def test_main_no_reports_no_redeploy(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert main(["--merge-reports", str(tmp_path / "none"), "--manifest", str(tmp_path / "m.json")]) == 0
    assert "redeploy=false" in out.read_text(encoding="utf-8")


# ── 教室學期（/rooms/** 教室課表頁，spec 2026-10-01）────────────────────────────

ROOMS_MANIFEST = {**SCHEDULE, "terms": {
    "114-1": {"catalog": "x"},                       # 舊學期沒有 rooms 鍵
    "114-2": {"catalog": "x", "rooms": None},        # 舊學期 rooms: null
    "115-1": {"catalog": "x", "rooms": "terms/115-1/rooms.json"},
    "115-2": {"catalog": "x", "rooms": None},
}}


def test_changed_rooms_terms(tmp_path):
    d = _reports(tmp_path, [
        {"name": "rooms", "term": "115-1", "changed": True},
        {"name": "rooms", "term": "114-2", "changed": False},
        {"name": "catalog", "term": "114-1", "changed": True},
    ])
    assert changed_rooms_terms(d) == {"115-1"}
    assert changed_rooms_terms(None) == set()


def test_resolve_room_term_current_with_rooms():
    # NOW＝12/01：預設已切 115-2，但本學期仍是 115-1 → 教室學期 115-1
    assert resolve_default_term(ROOMS_MANIFEST, NOW) == "115-2"
    assert resolve_room_term(ROOMS_MANIFEST, NOW) == "115-1"


def test_resolve_room_term_falls_back_to_latest_with_rooms():
    m = {**SCHEDULE, "terms": {
        "114-1": {"rooms": "a"}, "114-2": {"rooms": "b"}, "115-1": {"rooms": None}, "115-2": {}}}
    assert resolve_room_term(m, NOW) == "114-2"
    # 無 term_schedule → 本學期用日期規則（12/01 → 115-1）
    assert resolve_room_term({"terms": {"115-1": {"rooms": "r"}, "114-2": {"rooms": "r"}}}, NOW) == "115-1"


def test_resolve_room_term_none():
    assert resolve_room_term(None, NOW) is None
    assert resolve_room_term(SCHEDULE, NOW) is None                         # 無 terms
    assert resolve_room_term({**SCHEDULE, "terms": {"115-1": {"rooms": None}, "115-2": {}}}, NOW) is None


def test_decide_room_term_rooms_changed_triggers():
    ok, reason = decide(set(), "115-2", {"115-1"}, "115-1")
    assert ok and "教室學期 115-1" in reason and "rooms" in reason


def test_decide_room_term_catalog_changed_triggers_even_if_not_default():
    # 期中撤選截止後預設學期已切 115-2；115-1 catalog 有變 → hub 不需重建，但教室頁需要
    assert decide({"115-1"}, "115-2")[0] is False                           # 舊行為（無教室學期）
    ok, reason = decide({"115-1"}, "115-2", set(), "115-1")
    assert ok and "教室學期 115-1" in reason and "catalog" in reason


def test_decide_room_term_no_relevant_change():
    assert decide(set(), "115-2", set(), "115-1") == (False, "catalog／rooms 沒有內容變動")
    ok, reason = decide({"114-2"}, "115-2", {"114-1"}, "115-1")
    assert not ok and "114-1" in reason and "114-2" in reason


def test_decide_default_still_wins_with_room_term():
    ok, reason = decide({"115-2"}, "115-2", set(), "115-1")
    assert ok and "預設學期 115-2" in reason


def test_main_room_term_rooms_change(tmp_path, monkeypatch, capsys):
    d = _reports(tmp_path, [{"name": "rooms", "term": "115-1", "changed": True},
                            {"name": "enrollment", "term": "115-2", "changed": True}])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(ROOMS_MANIFEST), encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert main(["--merge-reports", str(d), "--manifest", str(manifest), "--now", NOW.isoformat()]) == 0
    assert "redeploy=true" in out.read_text(encoding="utf-8")
    assert "教室學期 115-1" in capsys.readouterr().out


def test_main_only_enrollment_no_redeploy(tmp_path, monkeypatch):
    d = _reports(tmp_path, [{"name": "enrollment", "term": "115-1", "changed": True},
                            {"name": "details", "term": "115-1", "changed": True}])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(ROOMS_MANIFEST), encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert main(["--merge-reports", str(d), "--manifest", str(manifest), "--now", NOW.isoformat()]) == 0
    assert "redeploy=false" in out.read_text(encoding="utf-8")


def test_main_no_rooms_terms_behaves_like_before(tmp_path, monkeypatch):
    """manifest 完全沒有 rooms 學期 → 只看預設學期 catalog（舊行為）。"""
    m = {**SCHEDULE, "terms": {"115-1": {"catalog": "x"}, "115-2": {"catalog": "x", "rooms": None}}}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(m), encoding="utf-8")
    for applied, expect in (
        ([{"name": "catalog", "term": "115-1", "changed": True},
          {"name": "rooms", "term": "115-1", "changed": True}], "redeploy=false"),
        ([{"name": "catalog", "term": "115-2", "changed": True}], "redeploy=true"),
    ):
        sub = tmp_path / expect / str(len(applied))
        sub.mkdir(parents=True)
        d = _reports(sub, applied)
        out = sub / "out"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        assert main(["--merge-reports", str(d), "--manifest", str(manifest), "--now", NOW.isoformat()]) == 0
        assert expect in out.read_text(encoding="utf-8")


# ============================================================ campus_gis（D28）

def test_gis_changed(tmp_path):
    from infra.web_redeploy import gis_changed
    d = _reports(tmp_path, [{"name": "campus_gis", "term": None, "changed": False}])
    assert gis_changed(d) is False
    _reports(tmp_path, [{"name": "campus_gis", "term": None, "changed": True}], "merge-report-y.json")
    assert gis_changed(d) is True
    assert gis_changed(None) is False


def test_decide_gis_change_needs_room_term():
    ok, reason = decide(set(), "115-2", set(), "115-1", gis=True)
    assert ok and "campus_gis" in reason
    assert decide(set(), "115-2", set(), None, gis=True)[0] is False
