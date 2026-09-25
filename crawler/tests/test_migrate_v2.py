"""一次性遷移 migrate-pipeline-v2（spec §7）：details／enrollment／fetch-state／reports，且冪等。"""
import json
import os
import subprocess

import pytest

from models import CourseDetail, LocalizedText, Syllabus
from ntut_catalog import enrollment_store as es
from ntut_catalog import fetch_state as fs
from ntut_catalog import registry
from ntut_catalog.cli import main
from ntut_catalog.detail import detail_line
from ntut_catalog.merge import merge_fetch_output
from ntut_catalog.migrate_v2 import migrate

T1 = "2026-09-01T00:00:00+08:00"      # 第一個 commit：課程結構、詳情、行事曆、標準
T2 = "2026-09-02T05:00:00+08:00"      # 第二個 commit：隔天的人數快照（catalog 沒變）


def _git(repo, *args, date=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def _legacy_rows(counts, observed_at):
    # 舊格式：列內帶 observed_at、**未排序**（舊版照爬取順序寫）
    return "".join(json.dumps({"offering_id": oid, "enrolled_count": n, "withdrawn_count": 0,
                               "observed_at": observed_at}) + "\n" for oid, n in counts)


def _legacy_detail_line(oid):
    d = CourseDetail(term_key="115-1", offering_id=oid, name=LocalizedText(zh="測試課程"),
                     syllabi=[Syllabus(teacher_code="T0001", teacher_name="測試教師",
                                       schedule="第1週：課程介紹")])
    raw = json.loads(d.model_dump_json())
    raw["generated_at"] = "2026-09-01T23:59:16+08:00"
    raw["syllabi"][0]["weekly_progress"] = {
        "status": "partial", "weeks": [], "notes": [], "parser_version": "progress/1.0.0",
        "parsed_at": "2026-09-01T23:59:16+08:00", "source_schedule_sha256": "x"}
    return json.dumps(raw, ensure_ascii=False) + "\n"


@pytest.fixture
def canonical(tmp_path):
    """舊形狀的 data branch checkout（git 工作區，兩個 commit）。"""
    c = tmp_path / "canonical"
    t = c / "115-1"
    (t / "enrollment").mkdir(parents=True)
    (t / "catalog.ndjson").write_text('{"offering_id":"300001"}\n{"offering_id":"300002"}\n',
                                      encoding="utf-8")
    (t / "classes.json").write_text("{}", encoding="utf-8")
    (t / "mprograms.json").write_text('{"term_key":"115-1","programs":[]}', encoding="utf-8")
    (t / "details.ndjson").write_text(_legacy_detail_line("300001") + _legacy_detail_line("300002"),
                                      encoding="utf-8")
    # 日檔 04:10 與時檔 18 點內容相同 → 後者去重；隔天內容不同
    (t / "enrollment" / "2026-09-01.ndjson").write_text(
        _legacy_rows([("300002", 5), ("300001", 3)], "2026-09-01T04:10:30+08:00"), encoding="utf-8")
    (t / "enrollment" / "2026-09-01T18.ndjson").write_text(
        _legacy_rows([("300001", 3), ("300002", 5)], "2026-09-01T18:05:00+08:00"), encoding="utf-8")
    (c / "calendar").mkdir()
    (c / "calendar" / "events.ndjson").write_text("{}\n", encoding="utf-8")
    (c / "calendar" / "meta.json").write_text("{}\n", encoding="utf-8")
    (t / "calendar.json").write_text("{}", encoding="utf-8")
    (c / "standards").mkdir()
    (c / "standards" / "115.json").write_text('{"entry_year":115}', encoding="utf-8")
    (c / "reports" / "115-1").mkdir(parents=True)
    (c / "reports" / "115-1" / "weekly-progress.json").write_text(json.dumps(
        {"schema_version": 1, "term_key": "115-1", "generated_at": T1,
         "parser_version": "progress/1.0.0"}, indent=1) + "\n", encoding="utf-8")
    _git(c, "init", "-q")
    _git(c, "add", "-A")
    _git(c, "commit", "-q", "-m", "day 1", date=T1)
    (t / "enrollment" / "2026-09-02.ndjson").write_text(
        _legacy_rows([("300002", 6), ("300001", 3)], "2026-09-02T04:00:59+08:00"), encoding="utf-8")
    _git(c, "add", "-A")
    _git(c, "commit", "-q", "-m", "day 2", date=T2)
    return c


def _tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file() and ".git" not in p.parts}


def test_details_strip_generated_at_and_weekly_progress(canonical):
    migrate(canonical)
    lines = (canonical / "115-1" / "details.ndjson").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        raw = json.loads(line)
        assert "generated_at" not in raw
        assert all("weekly_progress" not in s for s in raw["syllabi"])
        # 與新版 fetch 寫出的位元組一致：第一次重爬不會只因格式不同而整份變動
        assert line == detail_line(CourseDetail.model_validate_json(line))


def test_enrollment_renamed_by_in_row_observed_at_deduped_and_observed(canonical):
    summary = migrate(canonical)
    term_dir = canonical / "115-1"
    assert es.snapshots(term_dir) == ["2026-09-01T0410", "2026-09-02T0400"]
    assert not (term_dir / "enrollment" / "2026-09-01.ndjson").exists()
    assert summary.enrollment_terms["115-1"] == {"legacy_files": 3, "snapshots": 2,
                                                 "observations": 3}
    rows = [json.loads(l) for l in (term_dir / "enrollment" / "2026-09-01T0410.ndjson")
            .read_text(encoding="utf-8").splitlines()]
    assert rows == [{"offering_id": "300001", "enrolled_count": 3, "withdrawn_count": 0},
                    {"offering_id": "300002", "enrolled_count": 5, "withdrawn_count": 0}]
    # 每個原檔一筆觀測；被去重的時檔指向前一份
    assert es.observations(term_dir) == [
        {"observed_at": "2026-09-01T04:10:30+08:00", "snapshot": "2026-09-01T0410"},
        {"observed_at": "2026-09-01T18:05:00+08:00", "snapshot": "2026-09-01T0410"},
        {"observed_at": "2026-09-02T04:00:59+08:00", "snapshot": "2026-09-02T0400"},
    ]
    latest_rows, observed = es.latest(term_dir)
    assert observed == "2026-09-02T04:00:59+08:00"
    assert [r["enrolled_count"] for r in latest_rows] == [3, 6]


def test_fetch_state_times_from_git_and_hashes_like_merge(canonical):
    migrate(canonical)
    state = fs.load(fs.path_for(canonical))
    cat = fs.get(state, "catalog", "115-1")
    # changed_at＝內容檔最後 commit；checked_at＝writes（含人數快照）最後 commit
    assert cat["changed_at"] == T1
    assert cat["checked_at"] == T2
    ds = registry.DATASETS["catalog"]
    assert cat["content_sha256"] == fs.content_hash(
        registry.content_files(canonical, ds, "115-1"), canonical)
    det = fs.get(state, "details", "115-1")
    assert det["checked_at"] == det["changed_at"] == T1
    assert fs.get(state, "calendar", None)["changed_at"] == T1
    assert fs.get(state, "standards", None)["changed_at"] == T1
    assert fs.get(state, "mprograms", "115-1")["changed_at"] == T1
    enr = fs.get(state, "enrollment", "115-1")
    assert enr["changed_at"] == "2026-09-02T04:00:00+08:00"       # 最新快照檔名的時間
    assert enr["checked_at"] == "2026-09-02T04:00:59+08:00"       # 最後一筆觀測


def test_first_merge_after_migration_sees_unchanged_upstream(canonical, tmp_path):
    """遷移算的 hash 與 merge 一致：上游沒變 → changed=False、changed_at 不動。"""
    migrate(canonical)
    before = fs.get(fs.load(fs.path_for(canonical)), "catalog", "115-1")["changed_at"]
    stage = tmp_path / "stage"
    files = ["115-1/catalog.ndjson", "115-1/classes.json"]
    for rel in files:
        (stage / "canonical" / rel).parent.mkdir(parents=True, exist_ok=True)
        (stage / "canonical" / rel).write_bytes((canonical / rel).read_bytes())
    (stage / "pipeline-result.json").write_text(json.dumps({"cadence": "daily", "datasets": [
        {"name": "catalog", "term": "115-1", "ok": True, "checked_at": "2026-09-03T04:00:00+08:00",
         "error": None, "files": files}]}), encoding="utf-8")
    report = merge_fetch_output(stage, canonical.parent)
    assert report.applied == [{"name": "catalog", "term": "115-1", "changed": False}]
    after = fs.get(fs.load(fs.path_for(canonical)), "catalog", "115-1")
    assert after["changed_at"] == before
    assert after["checked_at"] == "2026-09-03T04:00:00+08:00"


def test_reports_strip_generated_at(canonical):
    migrate(canonical)
    rep = json.loads((canonical / "reports" / "115-1" / "weekly-progress.json").read_text("utf-8"))
    assert "generated_at" not in rep
    assert rep["parser_version"] == "progress/1.0.0"


def test_idempotent_second_run_is_noop(canonical):
    first = migrate(canonical)
    assert first.changed
    snapshot = _tree(canonical)
    second = migrate(canonical)
    assert not second.changed
    assert second.fetch_state == "exists"
    assert _tree(canonical) == snapshot


def test_mixed_old_and_new_enrollment_refuses(canonical):
    migrate(canonical)
    (canonical / "115-1" / "enrollment" / "2026-09-03.ndjson").write_text(
        _legacy_rows([("300001", 1)], "2026-09-03T04:00:00+08:00"), encoding="utf-8")
    with pytest.raises(RuntimeError, match="新舊格式混在一起"):
        migrate(canonical)


def test_cli(canonical, capsys):
    assert main(["migrate-pipeline-v2", "--data", str(canonical)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["fetch_state"] == "created"
    assert out["details_files"] == ["115-1/details.ndjson"]
