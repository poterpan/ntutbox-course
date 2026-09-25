"""infra/data_commit.py：只 commit 登錄表範圍內的檔，訊息由 merge 報告產生。"""
import json
import os
import subprocess

import pytest

from infra.data_commit import main, message_from_reports


def _git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=env).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "canonical"
    (r / "115-1" / "enrollment").mkdir(parents=True)
    (r / "115-1" / "catalog.ndjson").write_text("a\n", encoding="utf-8")
    (r / "115-1" / "enrollment" / "2026-09-01.ndjson").write_text("old\n", encoding="utf-8")
    _git(r, "init", "-q")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


def _reports(tmp_path, *reports):
    d = tmp_path / "reports"
    for i, rep in enumerate(reports):
        (d / f"s{i}").mkdir(parents=True)
        (d / f"s{i}" / "merge-report.json").write_text(json.dumps(rep), encoding="utf-8")
    return d


def test_commits_only_registry_scope_including_deletions(repo, tmp_path, monkeypatch):
    out = tmp_path / "gh-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    (repo / "115-1" / "catalog.ndjson").write_text("b\n", encoding="utf-8")
    (repo / "115-1" / "enrollment" / "2026-09-01.ndjson").unlink()          # 遷移式刪除
    (repo / "115-1" / "enrollment" / "2026-09-01T0410.ndjson").write_text("new\n", encoding="utf-8")
    (repo / "_meta").mkdir()
    (repo / "_meta" / "fetch-state.json").write_text("{}", encoding="utf-8")
    (repo / "stray.txt").write_text("x", encoding="utf-8")                    # 範圍外
    reports = _reports(tmp_path, {"datasets": ["catalog"], "terms": ["115-1"]},
                       {"datasets": ["mprograms", "catalog"], "terms": ["115-1"]})
    assert main(["--repo", str(repo), "--cadence", "daily", "--reports", str(reports)]) == 0
    assert _git(repo, "log", "-1", "--format=%s").strip() == "data(daily): catalog,mprograms 115-1"
    files = set(_git(repo, "show", "--name-only", "--format=", "HEAD").split())
    assert files == {"115-1/catalog.ndjson", "115-1/enrollment/2026-09-01.ndjson",
                     "115-1/enrollment/2026-09-01T0410.ndjson", "_meta/fetch-state.json"}
    assert "?? stray.txt" in _git(repo, "status", "--porcelain")
    assert "committed=true" in out.read_text(encoding="utf-8")


def test_no_diff_no_commit(repo, tmp_path, monkeypatch):
    out = tmp_path / "gh-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    (repo / "stray.txt").write_text("x", encoding="utf-8")
    head = _git(repo, "rev-parse", "HEAD")
    main(["--repo", str(repo), "--cadence", "daily"])
    assert _git(repo, "rev-parse", "HEAD") == head
    assert "committed=false" in out.read_text(encoding="utf-8")


def test_message_fallback_without_reports(repo, tmp_path):
    (repo / "reports" / "115-1").mkdir(parents=True)
    (repo / "reports" / "115-1" / "weekly-progress.json").write_text("{}", encoding="utf-8")
    main(["--repo", str(repo), "--cadence", "republish", "--message", "data(republish): reports"])
    assert _git(repo, "log", "-1", "--format=%s").strip() == "data(republish): reports"


def test_message_global_only_datasets(tmp_path):
    reports = _reports(tmp_path, {"datasets": ["calendar"], "terms": []})
    assert message_from_reports("daily", reports) == "data(daily): calendar"
