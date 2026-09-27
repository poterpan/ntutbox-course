"""infra/web_redeploy.py：publish 後要不要觸發 web 重新部署（D22）。"""
import datetime as dt
import json

from infra.web_redeploy import TAIPEI, changed_catalog_terms, decide, main, resolve_default_term

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
