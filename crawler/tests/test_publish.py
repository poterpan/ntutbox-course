import subprocess
from pathlib import Path

import pytest

from infra import publish
from infra.publish import cache_control_for, plan_uploads, quality_gate, r2_key


def test_r2_key_prefix():
    assert r2_key("v1/manifest.json") == "course/v1/manifest.json"
    assert r2_key("v1/terms/115-1/catalog.json") == "course/v1/terms/115-1/catalog.json"


def test_cache_control():
    assert "max-age=300" in cache_control_for("v1/manifest.json")
    assert "max-age=3600" in cache_control_for("v1/terms/115-1/catalog.json")
    assert "max-age=3600" in cache_control_for("v1/terms/115-1/classes.json")
    assert "max-age=300" in cache_control_for("v1/terms/115-1/enrollment.json")


def test_quality_gate():
    assert quality_gate(current=2440, previous=2450, min_ratio=0.95)[0] is True
    assert quality_gate(current=100, previous=200, min_ratio=0.95)[0] is False   # 掉 50%
    assert quality_gate(current=0, previous=0, min_ratio=0.95)[0] is False        # 0 課必擋
    assert quality_gate(current=2440, previous=0, min_ratio=0.95)[0] is True      # 首次（無基準）放行


def test_plan_uploads_manifest_last():
    files = [
        "v1/terms/115-1/catalog.json",
        "v1/manifest.json",
        "v1/terms/115-1/enrollment.json",
    ]
    plan = plan_uploads(files)
    assert plan[-1] == "v1/manifest.json"           # manifest 最後（原子性）
    assert set(plan) == set(files)


def test_v1_files_ignores_stray_files(tmp_path):
    """回歸：data/v1/terms/ 下的 .DS_Store 等非目錄不可被當成學期。"""
    from infra.publish import _v1_files_for
    td = tmp_path / "v1" / "terms" / "115-1"
    td.mkdir(parents=True)
    for n in ["catalog.json", "classes.json", "periods.json", "enrollment.json"]:
        (td / n).write_text("{}")
    (tmp_path / "v1" / "terms" / ".DS_Store").write_text("junk")  # 干擾檔
    files = _v1_files_for(tmp_path, None)  # --all 模式
    assert not any(".DS_Store" in f for f in files)
    assert "v1/manifest.json" in files
    assert sum(1 for f in files if f.startswith("v1/terms/115-1/")) == 4


# ── wrangler_put 重試（R2 偶發 500）─────────────────────────────
# 實測背景：crawl details #5（2026-08-16）在上傳第 6 個檔案時撞到
# Cloudflare 500 internal error（code 10001「Please try again」），
# 前 5 個已上傳、整個 workflow 掛掉。backfill 要上傳 11 學期 ×（6 檔 +
# 約 21,500 個 course/*.json），撞到的機率很高，必須能自己撐過去。

def test_wrangler_put_retries_then_succeeds(monkeypatch):
    calls = []

    def fake_run(cmd, check):
        calls.append(cmd)
        if len(calls) < 3:
            raise subprocess.CalledProcessError(1, cmd)
        return None

    monkeypatch.setattr(publish.subprocess, "run", fake_run)
    monkeypatch.setattr(publish.time, "sleep", lambda _s: None)  # 測試不要真的等
    publish.wrangler_put("b", "k", Path("f.json"), "cc", dry_run=False)
    assert len(calls) == 3, "前兩次失敗後應該重試到成功"


def test_wrangler_put_raises_after_exhausting_retries(monkeypatch):
    calls = []

    def always_fail(cmd, check):
        calls.append(cmd)
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(publish.subprocess, "run", always_fail)
    monkeypatch.setattr(publish.time, "sleep", lambda _s: None)
    with pytest.raises(subprocess.CalledProcessError):
        publish.wrangler_put("b", "k", Path("f.json"), "cc", dry_run=False)
    assert len(calls) == publish.UPLOAD_ATTEMPTS, "耗盡重試後要往外拋，不可吞掉"


def test_wrangler_put_dry_run_does_not_call_subprocess(monkeypatch):
    called = False

    def fake_run(cmd, check):
        nonlocal called
        called = True

    monkeypatch.setattr(publish.subprocess, "run", fake_run)
    publish.wrangler_put("b", "k", Path("f.json"), "cc", dry_run=True)
    assert not called
