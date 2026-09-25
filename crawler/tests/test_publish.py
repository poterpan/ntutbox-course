import json
import subprocess
from pathlib import Path

import pytest

from infra import publish
from infra.publish import cache_control_for, quality_gate, r2_key


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


def test_local_files_lists_everything_and_ignores_dotfiles(tmp_path):
    """全量比對：v1 底下每個檔都要列（含 course/ 詳情），`.DS_Store` 這類點檔不列。"""
    td = tmp_path / "v1" / "terms" / "115-1"
    (td / "course").mkdir(parents=True)
    for n in ["catalog.json", "classes.json", "course/1.json"]:
        (td / n).write_text("{}")
    (tmp_path / "v1" / "manifest.json").write_text("{}")
    (tmp_path / "v1" / "terms" / ".DS_Store").write_text("junk")
    (td / "course" / ".DS_Store").write_text("junk")
    assert publish.local_files(tmp_path) == [
        "v1/manifest.json", "v1/terms/115-1/catalog.json",
        "v1/terms/115-1/classes.json", "v1/terms/115-1/course/1.json"]


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


def test_parse_terms_arg_expands_ranges():
    assert publish.parse_terms_arg("110-1:111-1") == ["110-1", "110-2", "111-1"]


def test_parse_terms_arg_mixes_commas_and_ranges():
    assert publish.parse_terms_arg("115-1, 114-1:114-2") == ["115-1", "114-1", "114-2"]


@pytest.mark.parametrize("bad", ["", "115", "115-3", "abc", "115-1:"])
def test_parse_terms_arg_rejects_invalid(bad):
    with pytest.raises(ValueError):
        publish.parse_terms_arg(bad)


# ── S3 上傳（逐目錄 scope、Cache-Control 分組、manifest 最後）─────────────────

def test_s3_available_requires_all_credentials(monkeypatch):
    for k in ("R2_S3_ACCESS_KEY_ID", "R2_S3_SECRET_ACCESS_KEY", "CLOUDFLARE_ACCOUNT_ID"):
        monkeypatch.delenv(k, raising=False)
    assert publish.s3_available() is False
    monkeypatch.setenv("R2_S3_ACCESS_KEY_ID", "k")
    assert publish.s3_available() is False, "只有一個 key 不算可用"
    monkeypatch.setenv("R2_S3_SECRET_ACCESS_KEY", "s")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
    assert publish.s3_available() is True


def _seed(tmp_path, rels, body="{}"):
    for rel in rels:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def _upload_calls(monkeypatch, tmp_path, body, manifest_src=None):
    calls = []
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setattr(publish, "_run_aws", lambda cmd: calls.append(cmd))
    publish.s3_upload("bkt", tmp_path, body, manifest_src)
    return calls


def test_s3_groups_by_cache_control_and_keeps_manifest_last(monkeypatch, tmp_path):
    """manifest 最後推（原子性）；不同 Cache-Control 分批（--recursive 只能下同一個 metadata）。"""
    body = ["v1/terms/115-1/catalog.json", "v1/terms/115-1/enrollment.json",
            "v1/terms/115-1/course/1.json"]
    _seed(tmp_path, body)
    manifest = tmp_path / "stamped.json"
    manifest.write_text("{}")
    joined = [" ".join(c) for c in _upload_calls(monkeypatch, tmp_path, body, manifest)]
    assert "course/v1/manifest.json" in joined[-1], f"manifest 不在最後: {joined}"
    assert str(manifest) in joined[-1], "上傳的是蓋過時間的副本"
    assert any("max-age=300" in j for j in joined[:-1])
    assert any("max-age=3600" in j for j in joined[:-1])


def test_s3_whole_directory_needs_no_include_patterns(monkeypatch, tmp_path):
    """整個目錄都要傳時直接傳那個目錄——逐檔 include 的成本是 O(走訪檔數 × pattern 數)，
    11 學期 32,623 物件實測推算 68 小時。"""
    rels = [f"v1/terms/115-1/course/{i}.json" for i in range(400)]
    _seed(tmp_path, rels)
    calls = _upload_calls(monkeypatch, tmp_path, rels)
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd.count("--include") == 0
    assert str(tmp_path / "v1/terms/115-1/course") in cmd
    assert "s3://bkt/course/v1/terms/115-1/course/" in cmd


def test_s3_does_not_walk_unrelated_terms(monkeypatch, tmp_path):
    _seed(tmp_path, [f"v1/terms/110-1/course/{i}.json" for i in range(5)]
                    + [f"v1/terms/115-1/course/{i}.json" for i in range(5)])
    calls = _upload_calls(monkeypatch, tmp_path, [f"v1/terms/115-1/course/{i}.json" for i in range(5)])
    joined = " ".join(" ".join(c) for c in calls)
    assert "110-1" not in joined


def test_s3_partial_directory_uploads_exactly_the_listed_files(monkeypatch, tmp_path):
    _seed(tmp_path, [f"v1/terms/115-1/course/{i}.json" for i in range(5)])
    want = ["v1/terms/115-1/course/1.json", "v1/terms/115-1/course/3.json"]
    cmd = _upload_calls(monkeypatch, tmp_path, want)[0]
    assert cmd.count("--exclude") == 1 and cmd[cmd.index("--exclude") + 1] == "*"
    assert [cmd[i + 1] for i, x in enumerate(cmd) if x == "--include"] == ["1.json", "3.json"]


def test_s3_does_not_sweep_subdirectories_into_the_parent_batch(monkeypatch, tmp_path):
    """v1/terms/{t}/ 底下有 course/ 子目錄；傳 bulk 檔時不可裸 --recursive 把沒變的詳情一起掃上去。"""
    _seed(tmp_path, ["v1/terms/115-1/catalog.json", "v1/terms/115-1/classes.json",
                     "v1/terms/115-1/course/1.json"])
    cmd = _upload_calls(monkeypatch, tmp_path,
                        ["v1/terms/115-1/catalog.json", "v1/terms/115-1/classes.json"])[0]
    assert "--exclude" in cmd
    assert [cmd[i + 1] for i, x in enumerate(cmd) if x == "--include"] == ["catalog.json", "classes.json"]


# ── 差異比對 ──────────────────────────────────────────────────────────────

def _md5_of(tmp_path, rel):
    import hashlib
    return hashlib.md5((tmp_path / rel).read_bytes()).hexdigest()


def test_unchanged_rels_only_uploads_objects_whose_md5_differs(tmp_path):
    rels = [f"v1/terms/115-1/course/{i}.json" for i in range(4)]
    _seed(tmp_path, rels)
    (tmp_path / rels[1]).write_text('{"changed":1}', encoding="utf-8")
    remote = {r2_key(r): _md5_of(tmp_path, r) for r in rels}
    remote[r2_key(rels[1])] = "0" * 32            # 遠端還是舊內容
    del remote[r2_key(rels[2])]                   # 遠端沒有
    assert publish.unchanged_rels(tmp_path, rels, remote) == {rels[0], rels[3]}


def test_multipart_etag_never_counts_as_a_match(tmp_path):
    """multipart 物件的 ETag 是 <md5>-<段數>，不是內容 MD5——不可拿來判等。"""
    rels = ["v1/terms/115-1/course/9.json"]
    _seed(tmp_path, rels)
    remote = {r2_key(rels[0]): _md5_of(tmp_path, rels[0]) + "-3"}
    assert publish.unchanged_rels(tmp_path, rels, remote) == set()


# ── listing 分頁（Review Focus 3）──────────────────────────────────────────

class FakeS3:
    """假 S3：`aws s3api list-objects-v2 --max-items N [--starting-token T]` 的分頁行為。

    token 是不透明字串（這裡刻意不用數字，避免實作偷懶去猜 offset）。
    """

    def __init__(self, objects, page_size=1000):
        self.objects = sorted(objects.items())
        self.page_size = page_size
        self.list_calls = []

    def run_aws_json(self, cmd):
        assert cmd[:3] == ["aws", "s3api", "list-objects-v2"]
        assert cmd[cmd.index("--prefix") + 1] == "course/v1/"
        page_size = int(cmd[cmd.index("--max-items") + 1])
        token = cmd[cmd.index("--starting-token") + 1] if "--starting-token" in cmd else None
        self.list_calls.append(token)
        start = 0 if token is None else int(token.removeprefix("tok-").removesuffix("-x"))
        chunk = self.objects[start:start + min(page_size, self.page_size)]
        page = {"Contents": [{"Key": k, "ETag": f'"{v}"'} for k, v in chunk]}
        nxt = start + len(chunk)
        if nxt < len(self.objects):
            page["NextToken"] = f"tok-{nxt}-x"
        return page


def test_listing_walks_every_page_2500_objects(monkeypatch):
    objects = {f"course/v1/terms/115-1/course/{i:05d}.json": f"{i:032x}" for i in range(2500)}
    fake = FakeS3(objects)
    monkeypatch.setattr(publish, "_run_aws_json", fake.run_aws_json)
    got = publish.remote_etags("bkt", "https://ep")
    assert len(fake.list_calls) == 3, "2,500 物件、每頁 1000 → 3 頁"
    assert fake.list_calls[0] is None and fake.list_calls[1:] == ["tok-1000-x", "tok-2000-x"]
    assert got == objects, "第 1001 個以後的物件不可漏"


def test_full_listing_means_no_reupload_and_no_false_deletions(monkeypatch, tmp_path):
    """分頁完整 → 2,500 個內容相同的物件：零上傳、零刪除。漏頁會兩樣都錯。"""
    rels = [f"v1/terms/115-1/course/{i:05d}.json" for i in range(2500)]
    for i, rel in enumerate(rels):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f'{{"i":{i}}}', encoding="utf-8")
    objects = {r2_key(r): _md5_of(tmp_path, r) for r in rels}
    monkeypatch.setattr(publish, "_run_aws_json", FakeS3(objects).run_aws_json)
    remote = publish.remote_etags("bkt", "https://ep")
    assert publish.unchanged_rels(tmp_path, rels, remote) == set(rels)
    plan = publish.plan_deletions(rels, remote)
    assert plan.keys == [] and plan.skipped == {}


def test_listing_handles_empty_bucket(monkeypatch):
    monkeypatch.setattr(publish, "_run_aws_json", lambda cmd: {})
    assert publish.remote_etags("bkt", "https://ep") == {}


def test_listing_fails_on_a_repeated_token():
    """listing 壞掉（token 打轉）不可默默帶著半份清單繼續——半份清單會導致誤刪。"""
    with pytest.raises(RuntimeError):
        publish.list_all(lambda token: {"Contents": [], "NextToken": "same"})


def test_remote_etags_strips_quotes(monkeypatch):
    payload = {"Contents": [{"Key": "course/v1/a.json", "ETag": '"abc123"'},
                            {"Key": "course/v1/b.json", "ETag": "def456"}]}
    monkeypatch.setattr(publish, "_run_aws_json", lambda cmd: payload)
    assert publish.remote_etags("bkt", "https://ep") == {
        "course/v1/a.json": "abc123", "course/v1/b.json": "def456"}


# ── 過期刪除 ────────────────────────────────────────────────────────────

def test_deletion_prefix_only_allows_terms_standards_calendar():
    dp = publish.deletion_prefix
    assert dp("course/v1/terms/115-1/course/1.json") == "terms/115-1/"
    assert dp("course/v1/terms/115-1/catalog.json") == "terms/115-1/"
    assert dp("course/v1/standards/115.json") == "standards/"
    assert dp("course/v1/calendar/events.json") == "calendar/"
    assert dp("course/v1/manifest.json") is None                 # 根目錄永不動
    assert dp("course/v1/whatever.json") is None
    assert dp("course/v1/other/x.json") is None                  # 不在白名單的目錄
    assert dp("course/v1/terms/stray.json") is None              # terms/ 根
    assert dp("course/og.png") is None                           # v1 以外


def _remote_for(rels):
    return {r2_key(r): "0" * 32 for r in rels}


def test_stale_objects_are_deleted_only_inside_allowed_prefixes():
    local = [f"v1/terms/115-1/course/{i}.json" for i in range(20)] + ["v1/manifest.json"]
    remote = _remote_for(local + ["v1/terms/115-1/course/old.json",   # 過期 → 刪
                                  "v1/legacy.json",                   # 根目錄 → 不動
                                  "v1/other/x.json"])                 # 其他目錄 → 不動
    plan = publish.plan_deletions(local, remote)
    assert plan.keys == ["course/v1/terms/115-1/course/old.json"]
    assert plan.skipped == {}


def test_mass_deletion_in_one_prefix_is_skipped_but_others_proceed():
    keep = [f"v1/terms/115-1/course/{i}.json" for i in range(17)]
    gone = [f"v1/terms/115-1/course/g{i}.json" for i in range(3)]         # 3/20 = 15% > 10%
    other_keep = [f"v1/terms/114-2/course/{i}.json" for i in range(20)]
    other_gone = ["v1/terms/114-2/course/old.json"]                         # 1/21 < 10%
    plan = publish.plan_deletions(keep + other_keep, _remote_for(keep + gone + other_keep + other_gone))
    assert plan.skipped == {"terms/115-1/": (3, 20)}
    assert plan.keys == ["course/v1/terms/114-2/course/old.json"]


def test_exactly_ten_percent_is_not_mass_deletion():
    keep = [f"v1/standards/{i}.json" for i in range(9)]
    plan = publish.plan_deletions(keep, _remote_for(keep + ["v1/standards/old.json"]))  # 1/10
    assert plan.keys == ["course/v1/standards/old.json"] and plan.skipped == {}


def test_allow_mass_delete_releases_only_that_prefix():
    remote = _remote_for(["v1/terms/115-1/a.json", "v1/terms/114-2/a.json", "v1/calendar/events.json"])
    plan = publish.plan_deletions([], remote, {"terms/115-1/"})
    assert plan.keys == ["course/v1/terms/115-1/a.json"]
    assert set(plan.skipped) == {"terms/114-2/", "calendar/"}
    assert plan.allowed == {"terms/115-1/"}


@pytest.mark.parametrize("spec,want", [("115-1", "terms/115-1/"), ("terms/115-1/", "terms/115-1/"),
                                       ("standards", "standards/"), ("calendar/", "calendar/")])
def test_normalize_prefix(spec, want):
    assert publish.normalize_prefix(spec) == want


@pytest.mark.parametrize("bad", ["", "v1", "terms", "terms/115-3", "../x", "manifest.json"])
def test_normalize_prefix_rejects_everything_else(bad):
    with pytest.raises(ValueError):
        publish.normalize_prefix(bad)


# ── 品質閘門（基準＝線上 manifest 的 count）────────────────────────────────

def _man(**counts):
    return {"terms": {t.replace("_", "-"): {"catalog": {"count": n}} for t, n in counts.items()}}


def test_gate_with_baseline():
    assert publish.check_gate(_man(t115_1=2440), _man(t115_1=2450), ["t115-1"], 0.95) == []
    fails = publish.check_gate(_man(t115_1=12), _man(t115_1=2450), ["t115-1"], 0.95)
    assert [t for t, _ in fails] == ["t115-1"] and "dropped" in fails[0][1]


def test_gate_without_baseline_only_requires_nonzero():
    assert publish.check_gate(_man(t115_1=12), None, ["t115-1"], 0.95) == []
    # 線上有此學期但尚無 count（舊 manifest）→ 同樣只檢查不為 0
    live = {"terms": {"t115-1": {"catalog": {"url": "x"}}}}
    assert publish.check_gate(_man(t115_1=12), live, ["t115-1"], 0.95) == []


def test_gate_zero_courses_always_fails():
    assert publish.check_gate(_man(t115_1=0), None, ["t115-1"], 0.95)
    assert publish.check_gate(_man(), None, ["t115-1"], 0.95), "本地沒有該學期 → 0 課 → 擋"


def test_min_ratio_env_override(monkeypatch):
    monkeypatch.delenv("QUALITY_MIN_RATIO", raising=False)
    assert publish.min_ratio_from_env() == 0.95
    monkeypatch.setenv("QUALITY_MIN_RATIO", "")
    assert publish.min_ratio_from_env() == 0.95
    monkeypatch.setenv("QUALITY_MIN_RATIO", "0.5")
    assert publish.min_ratio_from_env() == 0.5
    monkeypatch.setenv("QUALITY_MIN_RATIO", "abc")
    with pytest.raises(ValueError):
        publish.min_ratio_from_env()


def test_fetch_live_manifest_missing_key_means_no_baseline(monkeypatch):
    monkeypatch.setenv("R2_S3_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("R2_S3_SECRET_ACCESS_KEY", "s")
    monkeypatch.setattr(publish.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 254, "", "An error occurred (NoSuchKey) when calling the GetObject operation"))
    assert publish.fetch_live_manifest("bkt", "https://ep") is None


def test_fetch_live_manifest_other_errors_are_loud(monkeypatch):
    """讀不到基準（例如憑證錯）不可當成「沒有基準」放行——那會讓閘門形同虛設。"""
    monkeypatch.setenv("R2_S3_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("R2_S3_SECRET_ACCESS_KEY", "s")
    monkeypatch.setattr(publish.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 254, "", "An error occurred (AccessDenied) when calling the GetObject operation"))
    with pytest.raises(RuntimeError):
        publish.fetch_live_manifest("bkt", "https://ep")


def test_fetch_live_manifest_uses_s3_getobject(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        Path(cmd[-1]).write_text('{"terms":{}}', encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("R2_S3_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("R2_S3_SECRET_ACCESS_KEY", "s")
    monkeypatch.setattr(publish.subprocess, "run", fake_run)
    assert publish.fetch_live_manifest("bkt", "https://ep") == {"terms": {}}
    assert seen["cmd"][:3] == ["aws", "s3api", "get-object"]
    assert seen["cmd"][seen["cmd"].index("--key") + 1] == "course/v1/manifest.json"


# ── main 端到端（假 aws）────────────────────────────────────────────────────

class FakeAws:
    """記錄 _run_aws 呼叫；listing 走 FakeS3；線上 manifest 由 live 指定。"""

    def __init__(self, monkeypatch, tmp_path, remote, live):
        self.calls = []
        self.uploaded_manifest = None
        for k, v in {"R2_S3_ACCESS_KEY_ID": "k", "R2_S3_SECRET_ACCESS_KEY": "s",
                     "CLOUDFLARE_ACCOUNT_ID": "acct"}.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("QUALITY_MIN_RATIO", raising=False)
        self.summary = tmp_path / "summary.md"
        self.output = tmp_path / "output.txt"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(self.summary))
        monkeypatch.setenv("GITHUB_OUTPUT", str(self.output))
        monkeypatch.setattr(publish, "_run_aws_json", FakeS3(remote).run_aws_json)
        monkeypatch.setattr(publish, "fetch_live_manifest", lambda b, e: live)
        monkeypatch.setattr(publish, "_run_aws", self.run)
        monkeypatch.setattr(publish, "now_iso", lambda: "2026-09-26T06:30:00+08:00")

    def run(self, cmd):
        self.calls.append(cmd)
        if "course/v1/manifest.json" in " ".join(cmd) and cmd[:3] == ["aws", "s3", "cp"]:
            self.uploaded_manifest = json.loads(Path(cmd[3]).read_text(encoding="utf-8"))

    def kinds(self):
        out = []
        for c in self.calls:
            j = " ".join(c)
            out.append("delete" if "delete-objects" in j else
                       "manifest" if "course/v1/manifest.json" in j else "upload")
        return out


def _local_v1(tmp_path, n_courses=20, count=2450):
    out = tmp_path / "data"
    rels = [f"v1/terms/115-1/course/{i}.json" for i in range(n_courses)] + ["v1/terms/115-1/catalog.json"]
    _seed(out, rels)
    (out / "v1" / "manifest.json").write_text(json.dumps(
        {"schema_version": 3, "generated_at": None, "published_at": None, "min_app_version": None,
         "terms": {"115-1": {"catalog": {"url": "terms/115-1/catalog.json", "count": count}}},
         "calendars": {}}), encoding="utf-8")
    return out, rels



def test_main_uploads_diff_then_manifest_then_deletes(monkeypatch, tmp_path):
    out, rels = _local_v1(tmp_path)
    remote = {r2_key(r): _md5_of(out, r) for r in rels}
    remote[r2_key(rels[0])] = "0" * 32                              # 這個變了
    remote["course/v1/terms/115-1/course/old.json"] = "f" * 32      # 過期（1/22 < 10%）
    remote["course/v1/manifest.json"] = "e" * 32
    fake = FakeAws(monkeypatch, tmp_path, remote, live={"terms": {"115-1": {"catalog": {"count": 2450}}}})
    assert publish.main(["--bucket", "bkt", "--out", str(out)]) == 0
    assert fake.kinds() == ["upload", "manifest", "delete"]
    up = " ".join(fake.calls[0])
    assert "--include 0.json" in up and "1.json" not in up
    assert fake.uploaded_manifest["published_at"] == fake.uploaded_manifest["generated_at"] \
        == "2026-09-26T06:30:00+08:00"
    # v1/manifest.json 本身不被改（derive 的確定性產物）
    assert json.loads((out / "v1" / "manifest.json").read_text())["published_at"] is None
    summary = fake.summary.read_text(encoding="utf-8")
    assert "course/v1/terms/115-1/course/old.json" in summary
    assert "deletions_skipped=\n" in fake.output.read_text()


def test_main_mass_delete_guard_still_uploads_manifest_and_signals(monkeypatch, tmp_path, capsys):
    out, rels = _local_v1(tmp_path, n_courses=10)
    remote = {r2_key(r): _md5_of(out, r) for r in rels}
    for i in range(5):                                             # 5/16 > 10%
        remote[f"course/v1/terms/115-1/course/gone{i}.json"] = "f" * 32
    fake = FakeAws(monkeypatch, tmp_path, remote, live=None)
    rc = publish.main(["--bucket", "bkt", "--out", str(out)])
    assert rc == publish.EXIT_DELETIONS_SKIPPED == 3
    assert fake.kinds() == ["manifest"], "內容都沒變只傳 manifest；刪除被跳過"
    assert "::error" in capsys.readouterr().out
    assert "deletions_skipped=terms/115-1/" in fake.output.read_text()
    assert "刪除保險觸發" in fake.summary.read_text(encoding="utf-8")


def test_main_allow_mass_delete_releases(monkeypatch, tmp_path):
    out, rels = _local_v1(tmp_path, n_courses=10)
    remote = {r2_key(r): _md5_of(out, r) for r in rels}
    for i in range(5):
        remote[f"course/v1/terms/115-1/course/gone{i}.json"] = "f" * 32
    fake = FakeAws(monkeypatch, tmp_path, remote, live=None)
    assert publish.main(["--bucket", "bkt", "--out", str(out), "--allow-mass-delete", "115-1"]) == 0
    assert fake.kinds() == ["manifest", "delete"]


def test_main_dry_run_touches_nothing(monkeypatch, tmp_path, capsys):
    out, rels = _local_v1(tmp_path, n_courses=10)
    remote = {"course/v1/terms/115-1/course/gone.json": "f" * 32}
    fake = FakeAws(monkeypatch, tmp_path, remote, live=None)
    assert publish.main(["--bucket", "bkt", "--out", str(out), "--dry-run"]) == 0
    assert fake.calls == []
    printed = capsys.readouterr().out
    assert "[dry-run] DELETE bkt/course/v1/terms/115-1/course/gone.json" not in printed  # 1/1 → 被保險擋
    assert "::warning" in printed
    assert "[dry-run] PUT bkt/course/v1/manifest.json" in printed


def test_main_gate_blocks_everything(monkeypatch, tmp_path):
    out, _ = _local_v1(tmp_path, count=12)                         # 上游殘缺：只抓到 12 門
    fake = FakeAws(monkeypatch, tmp_path, {}, live={"terms": {"115-1": {"catalog": {"count": 2450}}}})
    assert publish.main(["--bucket", "bkt", "--out", str(out)]) == 1
    assert fake.calls == []
    assert "品質閘門未通過" in fake.summary.read_text(encoding="utf-8")


def test_main_gate_ratio_can_be_overridden_by_env(monkeypatch, tmp_path):
    out, _ = _local_v1(tmp_path, count=1300)
    FakeAws(monkeypatch, tmp_path, {}, live={"terms": {"115-1": {"catalog": {"count": 2450}}}})
    monkeypatch.setenv("QUALITY_MIN_RATIO", "0.5")
    assert publish.main(["--bucket", "bkt", "--out", str(out)]) == 0


def test_main_requires_derived_v1(tmp_path, capsys):
    assert publish.main(["--bucket", "bkt", "--out", str(tmp_path)]) == 1
    assert "derive" in capsys.readouterr().err


def test_main_rejects_removed_flags(tmp_path):
    for flag in (["--all"], ["--include-details"], ["--previous-counts", "{}"], ["--min-ratio", "0.9"]):
        with pytest.raises(SystemExit):
            publish.main(["--bucket", "bkt", "--out", str(tmp_path), *flag])
