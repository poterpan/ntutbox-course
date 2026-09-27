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
    (["--web-redeploy", "failed（HTTP 503）"], "Deploy Hook）failed（HTTP 503）"),
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


def test_derive_report_warning_opens_issue(tmp_path):
    """derive --alerts 的檔（artifact derive-reports-*，D24）與 merge 報告放同一目錄。"""
    gh = FakeGh()
    d = tmp_path / "reports" / "derive-reports-commit-publish"
    d.mkdir(parents=True)
    (d / "derive-report.json").write_text(json.dumps({"alerts": [
        {"level": "warning", "name": "meeting-rooms", "term": "115-1", "message": "1 門課不一致"}]}),
        encoding="utf-8")
    _run(gh, "--needs-json", OK_NEEDS, "--merge-reports", str(tmp_path / "reports"))
    body = next(a for a in gh.calls if a[:2] == ["issue", "create"])[-1]
    assert "derive 警告 `meeting-rooms` 115-1：1 門課不一致" in body


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


def test_partial_node_failure_warning_is_listed_in_issue(tmp_path):
    """部分節點失敗、已從 HEAD 沿用（warning）也要進 issue——沿用舊資料要有人知道。"""
    gh = FakeGh()
    _run(gh, "--needs-json", OK_NEEDS, "--merge-reports", str(_reports(tmp_path, [
        {"name": "details", "term": "115-1", "level": "warning",
         "message": "details 115-1: 2/2727 個節點失敗，已從 HEAD 沿用 1 個：offering_id=360748；"
                    "HEAD 也沒有、本次缺漏 1 個：offering_id=360749"}])))
    body = next(a for a in gh.calls if a[:2] == ["issue", "create"])[-1]
    assert "merge 警告 `details` 115-1" in body
    assert "offering_id=360748" in body and "offering_id=360749" in body


def test_summary_lists_partial_nodes(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    stages = _stage(tmp_path, [
        {"name": "standards", "term": None, "ok": True, "node_total": 400,
         "failed_nodes": [{"year": 115, "matric": "7", "division": "59"}, {"year": 115, "matric": "5"}]},
        {"name": "catalog", "term": "115-1", "ok": True, "node_total": 200, "failed_nodes": [{"unit": "59"}]},
    ])
    d = tmp_path / "reports"
    d.mkdir()
    (d / "merge-report.json").write_text(json.dumps({
        "applied": [{"name": "standards", "term": None, "changed": False,
                     "partial": True, "failed_nodes": 2}],
        "dropped": [{"name": "catalog", "term": "115-1", "reason": "1/200 個節點失敗"}],
        "partial": [{"name": "standards", "term": None, "failed": 2, "node_total": 400,
                     "carried_forward": [{"year": 115, "matric": "7", "division": "59"}],
                     "missing": [{"year": 115, "matric": "5"}]}]}), encoding="utf-8")
    from infra.pipeline_alert import render_summary
    text = render_summary(stages, d)
    assert "| standards | _global | ⚠️ 2/400 節點失敗 | 已確認、未變；⚠️ 2 個節點沿用 HEAD／缺漏 |" in text
    assert "| catalog | 115-1 | ⚠️ 1/200 節點失敗 | 丟棄：1/200 個節點失敗 |" in text
    assert "| standards | _global | 2/400 | year=115/matric=7/division=59 | year=115/matric=5 |" in text


# ------------------------------------------------------------ season 排程（issue #111）

from infra.pipeline_alert import (  # noqa: E402
    SEASON_FRESHNESS_TITLE,
    cmd_season_catalog,
    cmd_season_freshness,
    season_catalog_title,
    unmatched_season_slots,
)


class _Args:
    def __init__(self, data):
        self.data = data


def _season_data(tmp_path, slots, catalogs=(), observations=None):
    data = tmp_path / "data"
    (data / "ops").mkdir(parents=True)
    (data / "ops" / "season-schedule.json").write_text(json.dumps(
        {"schema_version": 1, "calendar_sha256": "x", "slots": [
            {"at": at, "terms": terms, "windows": ["期中撤選"], "reason": "base"}
            for at, terms in slots]}), encoding="utf-8")
    for term in catalogs:
        (data / "canonical" / term).mkdir(parents=True, exist_ok=True)
        (data / "canonical" / term / "catalog.ndjson").write_text("{}\n", encoding="utf-8")
    for term, stamps in (observations or {}).items():
        d = data / "canonical" / term / "enrollment"
        d.mkdir(parents=True, exist_ok=True)
        (d / "observations.ndjson").write_text("".join(
            json.dumps({"observed_at": s, "snapshot": "x"}) + "\n" for s in stamps), encoding="utf-8")
    return data


SEASON_NOW = dt.datetime(2026, 11, 25, 6, 30, tzinfo=TAIPEI)


def test_season_catalog_alerts_only_for_imminent_windows(tmp_path):
    """115-2 的預選 12/07 在 14 天內、沒有 catalog → 開；116-1 遠在半年後 → 不開（噪音）。"""
    data = _season_data(tmp_path, [("2026-11-26T00:00:00+08:00", "115-1"),
                                   ("2026-12-07T00:00:00+08:00", "115-2"),
                                   ("2027-05-24T00:00:00+08:00", "116-1")], catalogs=["115-1"])
    gh = FakeGh()
    assert cmd_season_catalog(_Args(data), gh, now=SEASON_NOW) == 0
    assert set(gh.open) == {season_catalog_title("115-2")}
    create = next(a for a in gh.calls if a[:2] == ["issue", "create"])
    body = create[create.index("--body") + 1]
    assert "ACTIVE_TERMS" in body and "2026-12-07T00:00:00+08:00" in body


def test_season_catalog_auto_closes_when_catalog_appears(tmp_path):
    data = _season_data(tmp_path, [("2026-12-07T00:00:00+08:00", "115-2")], catalogs=["115-2"])
    gh = FakeGh({season_catalog_title("115-2"): 7, "[pipeline] daily 失敗": 8})
    cmd_season_catalog(_Args(data), gh, now=SEASON_NOW)
    assert gh.open == {"[pipeline] daily 失敗": 8}              # 只關自己那一類
    assert gh.verbs() == ["comment", "close"]


def test_season_catalog_without_schedule_is_noop(tmp_path):
    gh = FakeGh()
    assert cmd_season_catalog(_Args(tmp_path), gh, now=SEASON_NOW) == 0
    assert gh.calls == []


def test_season_freshness_matches_observations_within_an_hour(tmp_path):
    slots = [("2026-11-24T15:00:00+08:00", "115-1"),         # 窗口外（> 12h 前）
             ("2026-11-24T21:00:00+08:00", "115-1"),         # 有觀測
             ("2026-11-25T00:00:00+08:00", "115-1,115-2"),   # 115-2 沒有
             ("2026-11-25T03:00:00+08:00", "115-1"),         # 只有更晚（> at+1h）的觀測 → 不算
             ("2026-11-25T06:00:00+08:00", "115-1")]         # 未滿 1h 寬限 → 不看
    data = _season_data(tmp_path, slots, observations={
        "115-1": ["2026-11-24T21:02:10+08:00", "2026-11-25T00:01:30+08:00",
                  "2026-11-25T05:30:00+08:00"],
        "115-2": ["2026-11-24T23:59:00+08:00"]})             # 早於 at → 不算
    got = unmatched_season_slots(json.loads((data / "ops" / "season-schedule.json").read_text()),
                                 data / "canonical", SEASON_NOW)
    assert got == [("2026-11-25T00:00:00+08:00", ["115-2"]),
                   ("2026-11-25T03:00:00+08:00", ["115-1"])]
    gh = FakeGh()
    cmd_season_freshness(_Args(data), gh, now=SEASON_NOW)
    assert set(gh.open) == {SEASON_FRESHNESS_TITLE}
    create = next(a for a in gh.calls if a[:2] == ["issue", "create"])
    body = create[create.index("--body") + 1]
    assert "2026-11-25T03:00:00+08:00" in body and "wrangler tail ntutbox-season-scheduler" in body
    assert "token" in body


def test_season_freshness_resolves_when_all_matched_or_no_slots(tmp_path):
    data = _season_data(tmp_path, [("2026-11-25T03:00:00+08:00", "115-1")],
                        observations={"115-1": ["2026-11-25T03:04:00+08:00"]})
    gh = FakeGh({SEASON_FRESHNESS_TITLE: 9})
    cmd_season_freshness(_Args(data), gh, now=SEASON_NOW)
    assert gh.open == {}
    # 窗口內沒有觸發格（選課季以外）→ 沒有 issue 就什麼都不做
    gh2 = FakeGh()
    later = SEASON_NOW + dt.timedelta(days=30)
    cmd_season_freshness(_Args(data), gh2, now=later)
    assert gh2.verbs() == []


def test_season_subcommands_via_main(tmp_path, monkeypatch):
    data = _season_data(tmp_path, [])
    gh = FakeGh()
    assert main(["season-catalog", "--data", str(data)], gh=gh) == 0
    assert main(["season-freshness", "--data", str(data)], gh=gh) == 0
    assert gh.verbs() == []


@pytest.mark.parametrize("status", ["", "skipped", "no-hook", "triggered"])
def test_web_redeploy_non_failure_is_not_a_problem(status):
    gh = FakeGh()
    assert _run(gh, "--needs-json", OK_NEEDS, "--publish-exit", "0", "--web-redeploy", status) == 0
    assert gh.verbs() == []
