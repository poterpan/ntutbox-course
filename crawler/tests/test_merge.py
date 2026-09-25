"""merge：commit-publish job 在鎖內把 stage 合併進最新 data branch（spec §3 job 2）。"""
import json

import pytest

from ntut_catalog import enrollment_store as es
from ntut_catalog import fetch_state as fs
from ntut_catalog.merge import merge_fetch_output

A = [{"offering_id": f"30{i:04d}", "enrolled_count": i, "withdrawn_count": 0} for i in range(3)]
B = [dict(r, enrolled_count=r["enrolled_count"] + 1) for r in A]


def _catalog_lines(n, tag="x"):
    return "".join(json.dumps({"offering_id": f"30{i:04d}", "tag": tag}) + "\n" for i in range(n))


def _rows_text(rows):
    return "".join(json.dumps(r) + "\n" for r in rows)


def _stage(tmp_path, name, entries, files, cadence="daily"):
    """entries: pipeline-result 的 datasets；files: {canonical 相對路徑: 內容}。"""
    stage = tmp_path / name
    for rel, text in files.items():
        p = stage / "canonical" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (stage / "pipeline-result.json").write_text(
        json.dumps({"schema_version": 1, "cadence": cadence, "datasets": entries}), encoding="utf-8")
    return stage


def _entry(name, term, checked_at="2026-09-26T06:30:00+08:00", ok=True, files=(), **extra):
    e = {"name": name, "term": term, "ok": ok, "checked_at": checked_at if ok else None,
         "error": None if ok else "RuntimeError: boom", "files": list(files)}
    e.update(extra)
    return e


def _catalog_stage(tmp_path, name, term, n, observed_at, rows, cadence="daily", tag="x"):
    snap = es.stamp_of(observed_at)
    files = {f"{term}/catalog.ndjson": _catalog_lines(n, tag), f"{term}/classes.json": "{}",
             f"{term}/enrollment/{snap}.ndjson": _rows_text(rows)}
    return _stage(tmp_path, name, [_entry(
        "catalog", term, checked_at=observed_at, files=files,
        enrollment={"observed_at": observed_at, "snapshot": snap})], files, cadence)


def _enrollment_stage(tmp_path, name, term, observed_at, rows):
    snap = es.stamp_of(observed_at)
    files = {f"{term}/enrollment/{snap}.ndjson": _rows_text(rows)}
    return _stage(tmp_path, name, [_entry(
        "enrollment", term, checked_at=observed_at, files=files,
        enrollment={"observed_at": observed_at, "snapshot": snap})], files, "season")


@pytest.fixture
def data(tmp_path):
    """最新 data branch：115-1 有 100 課的 catalog。"""
    d = tmp_path / "data"
    t = d / "canonical" / "115-1"
    t.mkdir(parents=True)
    (t / "catalog.ndjson").write_text(_catalog_lines(100, "head"), encoding="utf-8")
    (t / "classes.json").write_text("{}", encoding="utf-8")
    return d


def _state(data):
    return fs.load(fs.path_for(data / "canonical"))


# ------------------------------------------------------------ Review Focus 1：上游殘缺

def test_catalog_below_ratio_is_dropped_but_other_datasets_merge(tmp_path, data, monkeypatch):
    monkeypatch.delenv("QUALITY_MIN_RATIO", raising=False)
    files = {"115-1/catalog.ndjson": _catalog_lines(12, "broken"), "115-1/classes.json": "{}",
             "115-1/enrollment/2026-09-26T0630.ndjson": _rows_text(A[:1]),
             "115-1/mprograms.json": '{"term_key":"115-1","programs":[]}'}
    stage = _stage(tmp_path, "stage", [
        _entry("catalog", "115-1", files=list(files)[:3],
               enrollment={"observed_at": "2026-09-26T06:30:00+08:00", "snapshot": "2026-09-26T0630"}),
        _entry("mprograms", "115-1", files=["115-1/mprograms.json"]),
    ], files)
    report = merge_fetch_output(stage, data)

    canon = data / "canonical" / "115-1"
    assert (canon / "catalog.ndjson").read_text(encoding="utf-8") == _catalog_lines(100, "head")
    assert not (canon / "enrollment").exists()               # 同次爬取的人數快照也不收
    assert (canon / "mprograms.json").exists()               # 其他資料集照常
    assert [(d["name"], d["term"]) for d in report.dropped] == [("catalog", "115-1")]
    assert "12" in report.alerts[0]["message"] and "100" in report.alerts[0]["message"]
    assert report.datasets() == ["mprograms"]
    assert fs.get(_state(data), "catalog", "115-1") is None  # 沒確認成功 → 不動 checked_at
    assert fs.get(_state(data), "mprograms", "115-1") is not None


def test_ratio_threshold_and_env_override(tmp_path, data, monkeypatch):
    monkeypatch.delenv("QUALITY_MIN_RATIO", raising=False)
    ok = _catalog_stage(tmp_path, "s1", "115-1", 95, "2026-09-26T06:30:00+08:00", A)
    assert not merge_fetch_output(ok, data).dropped               # 95 = 100 × 0.95 → 放行
    (data / "canonical" / "115-1" / "catalog.ndjson").write_text(_catalog_lines(100), encoding="utf-8")
    monkeypatch.setenv("QUALITY_MIN_RATIO", "0.99")
    low = _catalog_stage(tmp_path, "s2", "115-1", 98, "2026-09-27T06:30:00+08:00", A)
    assert merge_fetch_output(low, data).dropped


def test_zero_courses_is_dropped_even_without_head(tmp_path, data):
    stage = _catalog_stage(tmp_path, "s", "115-2", 0, "2026-09-26T06:30:00+08:00", [])
    report = merge_fetch_output(stage, data)
    assert report.dropped and not (data / "canonical" / "115-2").exists()


def test_new_term_without_head_is_accepted(tmp_path, data):
    stage = _catalog_stage(tmp_path, "s", "115-2", 3, "2026-09-26T06:30:00+08:00", A)
    report = merge_fetch_output(stage, data)
    assert not report.dropped and report.changed
    assert (data / "canonical" / "115-2" / "catalog.ndjson").exists()


# ------------------------------------------------------------ Review Focus 2：部分失敗

def test_failed_dataset_files_are_never_merged(tmp_path, data):
    files = {"115-1/details.ndjson": '{"half": "written"}\n',
             "115-1/mprograms.json": '{"term_key":"115-1","programs":[]}'}
    stage = _stage(tmp_path, "stage", [
        _entry("details", "115-1", ok=False, files=["115-1/details.ndjson"]),
        _entry("mprograms", "115-1", files=["115-1/mprograms.json"]),
    ], files)
    report = merge_fetch_output(stage, data)
    assert not (data / "canonical" / "115-1" / "details.ndjson").exists()
    assert (data / "canonical" / "115-1" / "mprograms.json").exists()
    assert report.dropped == [{"name": "details", "term": "115-1",
                               "reason": "fetch failed: RuntimeError: boom"}]
    assert fs.get(_state(data), "details", "115-1") is None


def test_files_outside_writes_are_rejected(tmp_path, data):
    files = {"115-1/mprograms.json": "{}", "115-1/catalog.ndjson": _catalog_lines(1)}
    stage = _stage(tmp_path, "stage", [
        _entry("mprograms", "115-1", files=["115-1/mprograms.json", "115-1/catalog.ndjson",
                                            "../escape.json"]),
    ], files)
    report = merge_fetch_output(stage, data)
    assert (data / "canonical" / "115-1" / "catalog.ndjson").read_text(encoding="utf-8") \
        == _catalog_lines(100, "head")
    assert len(report.alerts) == 2


# ------------------------------------------------------------ enrollment 去重＋觀測

def test_unchanged_enrollment_only_appends_an_observation(tmp_path, data):
    merge_fetch_output(_catalog_stage(tmp_path, "d1", "115-1", 100, "2026-09-26T06:30:00+08:00", A), data)
    report = merge_fetch_output(
        _catalog_stage(tmp_path, "d2", "115-1", 100, "2026-09-27T06:30:00+08:00", A), data)
    term_dir = data / "canonical" / "115-1"
    assert es.snapshots(term_dir) == ["2026-09-26T0630"]
    assert [o["snapshot"] for o in es.observations(term_dir)] == ["2026-09-26T0630"] * 2
    assert report.snapshots_created == [] and not report.changed
    st = fs.get(_state(data), "enrollment", "115-1")
    assert st["checked_at"] == "2026-09-27T06:30:00+08:00"
    assert st["changed_at"] == "2026-09-26T06:30:00+08:00"


def test_daily_and_season_with_stale_checkouts(tmp_path, data):
    """daily（06:30 觀測）與 season（06:31 觀測）都從同一份舊 checkout 出發、先後進鎖——
    season 先合併、daily 後合併。不丟觀測、不產生重複快照、changed_at 只前進一次。"""
    season = _enrollment_stage(tmp_path, "season", "115-1", "2026-09-26T06:31:00+08:00", B)
    daily = _catalog_stage(tmp_path, "daily", "115-1", 100, "2026-09-26T06:30:00+08:00", B)
    r1 = merge_fetch_output(season, data)
    state_after_first = fs.get(_state(data), "enrollment", "115-1")
    r2 = merge_fetch_output(daily, data)
    term_dir = data / "canonical" / "115-1"
    assert es.snapshots(term_dir) == ["2026-09-26T0631"]                 # 沒有重複快照
    assert [o["observed_at"] for o in es.observations(term_dir)] == [
        "2026-09-26T06:30:00+08:00", "2026-09-26T06:31:00+08:00"]         # 兩筆觀測都在
    assert r1.snapshots_created == ["115-1/enrollment/2026-09-26T0631.ndjson"]
    assert r2.snapshots_created == []
    st = fs.get(_state(data), "enrollment", "115-1")
    assert st["changed_at"] == state_after_first["changed_at"] == "2026-09-26T06:31:00+08:00"
    assert st["checked_at"] == "2026-09-26T06:31:00+08:00"               # 不往回撥
    rows, observed = es.latest(term_dir)
    assert rows == B and observed == "2026-09-26T06:31:00+08:00"


def test_catalog_changed_at_moves_once_across_two_runs(tmp_path, data):
    s1 = _catalog_stage(tmp_path, "a", "115-1", 100, "2026-09-26T06:30:00+08:00", A, tag="new")
    s2 = _catalog_stage(tmp_path, "b", "115-1", 100, "2026-09-26T07:30:00+08:00", A, tag="new")
    assert merge_fetch_output(s1, data).applied[0]["changed"] is True
    r2 = merge_fetch_output(s2, data)
    assert r2.applied[0]["changed"] is False
    st = fs.get(_state(data), "catalog", "115-1")
    assert st["changed_at"] == "2026-09-26T06:30:00+08:00"
    assert st["checked_at"] == "2026-09-26T07:30:00+08:00"


def test_fetch_state_merges_by_key(tmp_path, data):
    """合併只動本次的 (資料集, 學期)；其他鍵原封不動。"""
    state = fs.empty()
    fs.update(state, "details", "115-1", "d", "2026-09-21T03:00:00+08:00")
    fs.update(state, "catalog", "114-2", "c", "2026-09-20T03:00:00+08:00")
    fs.save(fs.path_for(data / "canonical"), state)
    merge_fetch_output(_catalog_stage(tmp_path, "s", "115-1", 100, "2026-09-26T06:30:00+08:00", A), data)
    after = _state(data)
    assert after["datasets"]["details"] == state["datasets"]["details"]
    assert after["datasets"]["catalog"]["114-2"] == state["datasets"]["catalog"]["114-2"]
    assert "115-1" in after["datasets"]["catalog"]


def test_report_shape(tmp_path, data):
    report = merge_fetch_output(
        _catalog_stage(tmp_path, "s", "115-1", 100, "2026-09-26T06:30:00+08:00", A), data)
    j = report.to_json()
    assert set(j) == {"cadence", "applied", "dropped", "alerts", "snapshots_created",
                      "partial", "changed", "datasets", "terms"}
    assert j["cadence"] == "daily" and j["datasets"] == ["catalog"] and j["terms"] == ["115-1"]
    json.dumps(j)


def test_cli_merge_writes_report(tmp_path, data, capsys):
    from ntut_catalog import cli
    stage = _catalog_stage(tmp_path, "s", "115-1", 100, "2026-09-26T06:30:00+08:00", A)
    assert cli.main(["merge", "--stage", str(stage), "--out", str(data)]) == 0
    on_disk = json.loads((stage / "merge-report.json").read_text(encoding="utf-8"))
    assert on_disk == json.loads(capsys.readouterr().out)
    assert on_disk["datasets"] == ["catalog"]
