"""horizon 告警：不足 → 開 issue；補上 → 關 issue。告警不阻斷發布。

gh 呼叫用手刻的假 callable 攔下（repo 不用 mock 套件，比照 tests/_fakes.py）。
"""
import json

import pytest

from infra.calendar_horizon_alert import TITLE, run


class FakeGh:
    def __init__(self, open_issue: str = ""):
        self.open_issue = open_issue
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["issue", "list"]:
            return self.open_issue
        if args[:2] == ["issue", "create"]:
            self.open_issue = "999"
        if args[:2] == ["issue", "close"]:
            self.open_issue = ""
        return ""

    def verbs(self):
        return [a[1] for a in self.calls if a[0] == "issue"]


def write_meta(tmp_path, ok: bool, max_start: str = "2027-07-03"):
    d = tmp_path / "canonical" / "calendar"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(
        json.dumps({"source": {}, "horizon": {"ok": ok, "max_start": max_start,
                                              "checked_at": "2026-09-16T04:00:00+08:00"}}),
        encoding="utf-8")


def test_noop_without_meta(tmp_path):
    gh = FakeGh()
    assert run(tmp_path, gh=gh) == 0
    assert gh.calls == []


def test_ok_and_no_issue_does_nothing(tmp_path):
    write_meta(tmp_path, ok=True)
    gh = FakeGh()
    run(tmp_path, gh=gh)
    assert gh.verbs() == ["list"]


def test_insufficient_opens_issue(tmp_path):
    write_meta(tmp_path, ok=False, max_start="2027-07-03")
    gh = FakeGh()
    run(tmp_path, gh=gh)
    assert gh.verbs() == ["list", "create"]
    create = next(a for a in gh.calls if a[1] == "create")
    assert create[create.index("--title") + 1] == TITLE
    body = create[create.index("--body") + 1]
    assert "2027-07-03" in body
    assert "不阻斷發布" in body


def test_insufficient_does_not_open_duplicate(tmp_path):
    write_meta(tmp_path, ok=False)
    gh = FakeGh(open_issue="123")
    run(tmp_path, gh=gh)
    assert gh.verbs() == ["list"]          # 已經開著就不再開一個


def test_recovery_comments_and_closes(tmp_path):
    write_meta(tmp_path, ok=True, max_start="2028-07-02")
    gh = FakeGh(open_issue="123")
    run(tmp_path, gh=gh)
    assert gh.verbs() == ["list", "comment", "close"]
    comment = next(a for a in gh.calls if a[1] == "comment")
    assert "2028-07-02" in comment[comment.index("--body") + 1]


@pytest.mark.parametrize("ok", [True, False])
def test_always_exits_zero(tmp_path, ok):
    """horizon 不足是告警不是失敗——回非 0 會讓 workflow 紅燈、蓋掉真正的錯誤。"""
    write_meta(tmp_path, ok=ok)
    assert run(tmp_path, gh=FakeGh()) == 0
