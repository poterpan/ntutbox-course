"""infra/pipeline_alert.py：run 失敗與資料過期兩種 issue 的開／更新／關閉（假 gh）。"""
import datetime as dt
import json

import pytest

from infra.pipeline_alert import LABEL, TAIPEI, main, run_title, stale_title


class FakeGh:
    """記下呼叫；issue list 回傳目前開著的（依標題）。"""

    def __init__(self, open_issues=None):
        self.open = dict(open_issues or {})      # title -> number
        self.calls = []
        self._next = 100

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps([{"number": n, "title": t} for t, n in self.open.items()])
        if args[:2] == ["issue", "create"]:
            self.open[args[args.index("--title") + 1]] = self._next
            self._next += 1
        if args[:2] == ["issue", "close"]:
            self.open = {t: n for t, n in self.open.items() if str(n) != args[2]}
        return ""

    def verbs(self):
        return [a[1] for a in self.calls if a[0] == "issue" and a[1] != "list"]


def _stage(tmp_path, datasets):
    d = tmp_path / "stages" / "stage-daily"
    d.mkdir(parents=True)
    (d / "pipeline-result.json").write_text(json.dumps({"cadence": "daily", "datasets": datasets}),
                                            encoding="utf-8")
    return tmp_path / "stages"


def _reports(tmp_path, alerts):
    d = tmp_path / "reports"
    d.mkdir()
    (d / "merge-report-daily.json").write_text(json.dumps({"alerts": alerts}), encoding="utf-8")
    return d


OK_NEEDS = json.dumps({"fetch": {"result": "success"}, "commit-publish": {"result": "success"}})


def _run(gh, *extra):
    return main(["run", "--workflow", "daily", "--run-url", "https://example/run/1", *extra], gh=gh)


def test_all_success_without_issue_does_nothing(tmp_path):
    gh = FakeGh()
    assert _run(gh, "--needs-json", OK_NEEDS, "--stages", str(_stage(tmp_path, [
        {"name": "catalog", "term": "115-1", "ok": True}])), "--publish-exit", "0") == 0
    assert gh.verbs() == []


def test_failed_dataset_opens_labelled_issue_with_details(tmp_path):
    gh = FakeGh()
    stages = _stage(tmp_path, [{"name": "mprograms", "term": "115-1", "ok": False,
                                "error": "RuntimeError: boom"}])
    assert _run(gh, "--needs-json", OK_NEEDS, "--stages", str(stages)) == 0
    create = next(a for a in gh.calls if a[:2] == ["issue", "create"])
    assert create[create.index("--title") + 1] == run_title("daily")
    assert create[create.index("--label") + 1] == LABEL
    body = create[create.index("--body") + 1]
    assert "mprograms" in body and "115-1" in body and "boom" in body and "example/run/1" in body


@pytest.mark.parametrize("extra, needle", [
    (["--needs-json", json.dumps({"fetch": {"result": "failure"}})], "job `fetch`：failure"),
    (["--publish-exit", "3", "--deletions-skipped", "terms/115-1/"], "刪除保險"),
    (["--publish-exit", "1"], "publish exit 1"),
])
def test_other_failure_kinds_open_issue(tmp_path, extra, needle):
    gh = FakeGh()
    _run(gh, *extra)
    body = next(a for a in gh.calls if a[:2] == ["issue", "create"])[-1]
    assert needle in body


def test_merge_alert_opens_issue(tmp_path):
    gh = FakeGh()
    _run(gh, "--needs-json", OK_NEEDS, "--merge-reports", str(_reports(tmp_path, [
        {"name": "catalog", "term": "115-1", "message": "課數 12 < HEAD 2778 × 0.95"}])))
    assert "課數 12" in next(a for a in gh.calls if a[:2] == ["issue", "create"])[-1]


def test_repeat_failure_comments_instead_of_duplicating(tmp_path):
    gh = FakeGh({run_title("daily"): 7})
    _run(gh, "--publish-exit", "1")
    assert gh.verbs() == ["comment"]
    assert gh.calls[-1][2] == "7"


def test_recovery_comments_and_closes(tmp_path):
    gh = FakeGh({run_title("daily"): 7, run_title("weekly"): 8})
    _run(gh, "--needs-json", OK_NEEDS)
    assert gh.verbs() == ["comment", "close"]
    assert gh.open == {run_title("weekly"): 8}          # 別的 workflow 的 issue 不動


def _state(tmp_path, datasets):
    p = tmp_path / "data" / "canonical" / "_meta" / "fetch-state.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"schema_version": 1, "datasets": datasets}), encoding="utf-8")
    return tmp_path / "data"


NOW = dt.datetime(2026, 9, 26, 12, 0, tzinfo=TAIPEI)
CADENCES = {"catalog": "daily", "details": "weekly", "enrollment": "season"}


def _stale(gh, data):
    from infra.pipeline_alert import cmd_stale

    class A:
        pass
    a = A()
    a.data = data
    return cmd_stale(a, gh, cadences=CADENCES, now=NOW)


def test_stale_thresholds_daily_2d_weekly_9d_uses_newest_term(tmp_path):
    data = _state(tmp_path, {
        # 舊學期很久沒確認，但最新的 115-1 昨天確認過 → 不算過期
        "catalog": {"110-1": {"checked_at": "2026-06-14T03:00:00+08:00"},
                    "115-1": {"checked_at": "2026-09-25T06:00:00+08:00"}},
        "details": {"115-1": {"checked_at": "2026-09-16T06:00:00+08:00"}},   # 10 天
        "enrollment": {"115-1": {"checked_at": "2026-01-01T00:00:00+08:00"}},  # season 不查
    })
    gh = FakeGh()
    _stale(gh, data)
    titles = [a[a.index("--title") + 1] for a in gh.calls if a[:2] == ["issue", "create"]]
    assert titles == [stale_title("details")]


def test_stale_missing_dataset_counts_and_recovery_closes(tmp_path):
    data = _state(tmp_path, {"details": {"115-1": {"checked_at": "2026-09-25T06:00:00+08:00"}}})
    gh = FakeGh({stale_title("details"): 3})
    _stale(gh, data)
    assert stale_title("catalog") in gh.open               # 從未確認 → 過期
    assert stale_title("details") not in gh.open           # 恢復 → 關閉


def test_stale_without_fetch_state_is_noop(tmp_path):
    gh = FakeGh()
    assert main(["stale", "--data", str(tmp_path)], gh=gh) == 0
    assert gh.calls == []


def test_dry_run_env_does_not_call_gh(tmp_path, monkeypatch, capsys):
    from infra import pipeline_alert
    monkeypatch.setenv("PIPELINE_ALERT_DRY_RUN", "1")
    monkeypatch.setattr(pipeline_alert, "_gh", lambda args: pytest.fail("gh called"))
    assert pipeline_alert.main(["run", "--workflow", "daily", "--run-url", "u",
                                "--publish-exit", "1"]) == 0
    assert "[dry-run] gh issue create" in capsys.readouterr().out


def test_summary_table_lists_each_dataset(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    stages = _stage(tmp_path, [{"name": "catalog", "term": "115-1", "ok": True},
                               {"name": "calendar", "term": None, "ok": True},
                               {"name": "mprograms", "term": "115-1", "ok": False, "error": "boom"}])
    d = tmp_path / "reports"
    d.mkdir()
    (d / "merge-report.json").write_text(json.dumps({
        "applied": [{"name": "calendar", "term": None, "changed": False}],
        "dropped": [{"name": "catalog", "term": "115-1", "reason": "課數不足"}]}), encoding="utf-8")
    assert main(["summary", "--stages", str(stages), "--merge-reports", str(d)]) == 0
    text = summary.read_text(encoding="utf-8")
    assert "| catalog | 115-1 | ✅ | 丟棄：課數不足 |" in text
    assert "| calendar | _global | ✅ | 已確認、未變 |" in text
    assert "| mprograms | 115-1 | ❌ boom | — |" in text
