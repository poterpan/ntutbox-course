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
# ── S3 批次同步（backfill 用；wrangler 逐檔 put 撐不住 26,840 個 course/*.json）──

def test_s3_available_requires_all_credentials(monkeypatch):
    for k in ("R2_S3_ACCESS_KEY_ID", "R2_S3_SECRET_ACCESS_KEY", "CLOUDFLARE_ACCOUNT_ID"):
        monkeypatch.delenv(k, raising=False)
    assert publish.s3_available() is False
    monkeypatch.setenv("R2_S3_ACCESS_KEY_ID", "k")
    assert publish.s3_available() is False, "只有一個 key 不算可用"
    monkeypatch.setenv("R2_S3_SECRET_ACCESS_KEY", "s")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
    assert publish.s3_available() is True


def test_s3_groups_by_cache_control_and_keeps_manifest_last(monkeypatch):
    """同步必須維持原子性：manifest 最後推。且不同 Cache-Control 要分批
    （aws s3 cp --recursive 只能對整批下同一個 metadata）。"""
    calls = []
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")  # _s3_endpoint 需要
    monkeypatch.setattr(publish, "_run_aws", lambda cmd: calls.append(cmd))
    monkeypatch.setattr(publish, "remote_etags", lambda *a, **k: {})  # 這條測分組，不測差異
    files = [
        "v1/terms/115-1/catalog.json",
        "v1/terms/115-1/enrollment.json",
        "v1/terms/115-1/course/1.json",
        "v1/manifest.json",
    ]
    publish.s3_sync_upload("bkt", Path("/tmp/out"), files, dry_run=False)
    joined = [" ".join(c) for c in calls]
    assert any("manifest.json" in j for j in joined)
    # manifest 必須在最後一個呼叫
    assert "manifest.json" in joined[-1], f"manifest 不在最後: {joined}"
    # enrollment 用短快取、catalog 用長快取 → 至少要分開的呼叫
    assert any("max-age=300" in j for j in joined)
    assert any("max-age=3600" in j for j in joined)


def test_s3_sync_dry_run_makes_no_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(publish, "_run_aws", lambda cmd: calls.append(cmd))
    publish.s3_sync_upload("bkt", Path("/tmp/out"), ["v1/manifest.json"], dry_run=True)
    assert calls == []


# ── 逐目錄 scope（取代逐檔 --include；見 s3_sync_upload 的註解）──────────────

def _seed(tmp_path, rels):
    for rel in rels:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")


def _aws_calls(monkeypatch, tmp_path, files):
    calls = []
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setattr(publish, "_run_aws", lambda cmd: calls.append(cmd))
    monkeypatch.setattr(publish, "remote_etags", lambda *a, **k: {})   # 這組測的是指令形狀
    publish.s3_sync_upload("bkt", tmp_path, files, dry_run=False)
    return calls


def test_s3_whole_directory_needs_no_include_patterns(monkeypatch, tmp_path):
    """整個目錄都要傳時，就直接傳那個目錄——不要逐檔 --include。

    逐檔 include 的成本是 O(走訪檔數 × pattern 數)：11 學期 32,623 個物件時
    約 10.7 億次比對，實測 8 檔/分（推算 68 小時），比它取代的 wrangler 逐檔
    還慢。這條測試就是釘住「pattern 數不隨檔案數成長」。
    """
    rels = [f"v1/terms/115-1/course/{i}.json" for i in range(400)]
    _seed(tmp_path, rels)
    calls = _aws_calls(monkeypatch, tmp_path, rels)
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd.count("--include") == 0, "整個目錄都要傳時不該出現任何 --include"
    assert str(tmp_path / "v1/terms/115-1/course") in cmd, "來源要 scope 到該目錄"
    assert "s3://bkt/course/v1/terms/115-1/course/" in cmd


def test_s3_does_not_walk_unrelated_terms(monkeypatch, tmp_path):
    """只發 115-1 時，指令不該把其他學期的目錄當來源——那是 68 小時的來源。"""
    _seed(tmp_path, [f"v1/terms/110-1/course/{i}.json" for i in range(5)]
                    + [f"v1/terms/115-1/course/{i}.json" for i in range(5)])
    calls = _aws_calls(monkeypatch, tmp_path, [f"v1/terms/115-1/course/{i}.json" for i in range(5)])
    joined = " ".join(" ".join(c) for c in calls)
    assert "110-1" not in joined
    assert str(tmp_path) + " " not in joined + " ", "來源不該是整個 out_dir"


def test_s3_partial_directory_still_uploads_exactly_the_listed_files(monkeypatch, tmp_path):
    """只要傳目錄裡的一部分時，仍然只傳指名的那些——精確性不能為了速度讓步。"""
    _seed(tmp_path, [f"v1/terms/115-1/course/{i}.json" for i in range(5)])
    want = ["v1/terms/115-1/course/1.json", "v1/terms/115-1/course/3.json"]
    cmd = _aws_calls(monkeypatch, tmp_path, want)[0]
    assert cmd.count("--exclude") == 1 and cmd[cmd.index("--exclude") + 1] == "*"
    assert [cmd[i + 1] for i, x in enumerate(cmd) if x == "--include"] == ["1.json", "3.json"]


def test_s3_does_not_sweep_subdirectories_into_the_parent_batch(monkeypatch, tmp_path):
    """v1/terms/{t}/ 底下有 course/ 子目錄。傳 bulk 檔時若無條件 --recursive，
    會把 2,700 個 course/*.json 一起傳上去——等於 --include-details 失效。"""
    _seed(tmp_path, ["v1/terms/115-1/catalog.json",
                     "v1/terms/115-1/classes.json",
                     "v1/terms/115-1/course/1.json"])
    cmd = _aws_calls(monkeypatch, tmp_path,
                     ["v1/terms/115-1/catalog.json", "v1/terms/115-1/classes.json"])[0]
    assert "--exclude" in cmd, "有子目錄時必須明確排除，不能裸 --recursive"
    assert [cmd[i + 1] for i, x in enumerate(cmd) if x == "--include"] == ["catalog.json", "classes.json"]


# ── 差異上傳：沒變動的物件不重傳 ────────────────────────────────────────

def _with_remote(monkeypatch, tmp_path, files, remote, **kw):
    calls = []
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setattr(publish, "_run_aws", lambda cmd: calls.append(cmd))
    monkeypatch.setattr(publish, "remote_etags", lambda *a, **k: remote)
    publish.s3_sync_upload("bkt", tmp_path, files, dry_run=False, **kw)
    return " ".join(" ".join(c) for c in calls)


def _md5_of(tmp_path, rel):
    import hashlib
    return hashlib.md5((tmp_path / rel).read_bytes()).hexdigest()


def test_skips_objects_whose_etag_already_matches(monkeypatch, tmp_path):
    """#89/#95 讓沒變動的產物 byte-identical，發佈端本來就不該重傳它們。
    ETag = 內容 MD5（2026-09-20 對 cdn.ntutbox.com 實測驗證）。"""
    rels = [f"v1/terms/115-1/course/{i}.json" for i in range(3)]
    _seed(tmp_path, rels)
    remote = {publish.r2_key(r): _md5_of(tmp_path, r) for r in rels}
    joined = _with_remote(monkeypatch, tmp_path, rels, remote)
    assert joined == "", "全部都沒變，不該有任何上傳指令"


def test_uploads_the_ones_that_differ(monkeypatch, tmp_path):
    rels = [f"v1/terms/115-1/course/{i}.json" for i in range(3)]
    _seed(tmp_path, rels)
    (tmp_path / rels[1]).write_text('{"changed":1}', encoding="utf-8")
    remote = {publish.r2_key(r): _md5_of(tmp_path, r) for r in rels}
    remote[publish.r2_key(rels[1])] = "0" * 32          # 遠端還是舊內容
    joined = _with_remote(monkeypatch, tmp_path, rels, remote)
    assert "--include 1.json" in joined
    assert "0.json" not in joined and "2.json" not in joined


def test_uploads_objects_missing_remotely(monkeypatch, tmp_path):
    rels = ["v1/terms/115-1/course/7.json"]
    _seed(tmp_path, rels)
    joined = _with_remote(monkeypatch, tmp_path, rels, {})
    assert "v1/terms/115-1/course" in joined, "遠端沒有這個物件 → 必須上傳"


def test_multipart_etag_never_counts_as_a_match(monkeypatch, tmp_path):
    """multipart 物件的 ETag 是 <md5>-<段數>，不是內容 MD5——不可拿來判等。"""
    rels = ["v1/terms/115-1/course/9.json"]
    _seed(tmp_path, rels)
    remote = {publish.r2_key(rels[0]): _md5_of(tmp_path, rels[0]) + "-3"}
    assert "v1/terms/115-1/course" in _with_remote(monkeypatch, tmp_path, rels, remote)


def test_manifest_is_always_pushed_even_when_unchanged(monkeypatch, tmp_path):
    """manifest 是「東西都就緒了」的信號，不參與跳過。"""
    rels = ["v1/manifest.json"]
    _seed(tmp_path, rels)
    remote = {publish.r2_key(rels[0]): _md5_of(tmp_path, rels[0])}
    assert "manifest.json" in _with_remote(monkeypatch, tmp_path, rels, remote)


def test_skipping_can_be_turned_off(monkeypatch, tmp_path):
    """改 Cache-Control 之類「內容沒變但 metadata 要變」的情況需要強制全傳。"""
    rels = ["v1/terms/115-1/course/1.json"]
    _seed(tmp_path, rels)
    remote = {publish.r2_key(rels[0]): _md5_of(tmp_path, rels[0])}
    assert "v1/terms/115-1/course" in _with_remote(
        monkeypatch, tmp_path, rels, remote, skip_unchanged=False)


def test_remote_etags_parses_listing_and_strips_quotes(monkeypatch):
    payload = {"Contents": [{"Key": "course/v1/a.json", "ETag": '"abc123"'},
                            {"Key": "course/v1/b.json", "ETag": "def456"}]}
    monkeypatch.setattr(publish, "_run_aws_json", lambda cmd: payload)
    assert publish.remote_etags("bkt", "https://ep") == {
        "course/v1/a.json": "abc123", "course/v1/b.json": "def456"}


def test_parse_terms_arg_expands_ranges():
    assert publish.parse_terms_arg("110-1:111-1") == ["110-1", "110-2", "111-1"]


def test_parse_terms_arg_mixes_commas_and_ranges():
    assert publish.parse_terms_arg("115-1, 114-1:114-2") == ["115-1", "114-1", "114-2"]


@pytest.mark.parametrize("bad", ["", "115", "115-3", "abc", "115-1:"])
def test_parse_terms_arg_rejects_invalid(bad):
    with pytest.raises(ValueError):
        publish.parse_terms_arg(bad)
