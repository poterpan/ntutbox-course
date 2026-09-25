"""發佈 v1 到 Cloudflare R2：品質閘門 → 全量比對 → 差異上傳 → manifest → 過期刪除。

publish 層只做「v1 → R2」（spec §1）：**不重建 v1**。輸入是 `python -m ntut_catalog derive
--out data` 產出的 `data/v1/`，所以 workflow 一律先 derive 再 publish。

流程：
  1. 品質閘門：本地 manifest 各學期 catalog `count` 對**線上** manifest 的 `count`
     （S3 GetObject 直讀 bucket，不走 CDN 的 max-age=300 快取）。低於 基準 × 門檻 或為 0 → 不發佈、exit 1。
     門檻預設 0.95，環境變數 `QUALITY_MIN_RATIO` 可覆寫；線上無此學期或尚無 `count` → 只檢查「不為 0」。
  2. 全量比對：分頁列出 `course/v1/` 全部物件（約 3.3 萬、33 頁），與本地 `v1/` 逐檔 MD5 比對，
     只傳不同者（multipart ETag `<md5>-<n>` 一律視為不同）。`--no-skip-unchanged` 全部重傳。
  3. manifest 上傳前寫入 `published_at` = `generated_at` = 現在（+08:00），永遠最後推（原子性）。
     時間只蓋在上傳的副本上，`v1/manifest.json` 維持 derive 的確定性產物。
  4. 過期刪除：只在 `terms/<t>/`、`standards/`、`calendar/` 這些 prefix 內（**永不動 v1 根目錄**，
     其他目錄也不動），R2 有而本地沒有 → 刪除。manifest 推完才刪，client 不會被指向已刪的物件。
     保險：單一 prefix 刪除量 > 該 prefix 遠端物件數 10% → **跳過該 prefix 的刪除**，其餘照常
     （含 manifest），並告警；人工確認後以 `--allow-mass-delete <prefix>` 放行。

告警訊號（10% 保險觸發時）：
  **上傳與其他 prefix 的刪除全部完成後，以 exit code 3 結束**（EXIT_DELETIONS_SKIPPED），並輸出
  `::error` annotation、`$GITHUB_STEP_SUMMARY` 的跳過清單、`$GITHUB_OUTPUT` 的
  `deletions_skipped=<prefix,...>`。選 exit code 而不是只寫 summary：現行 workflow 還沒有開 issue
  的告警元件（spec §3 的 alert 是後續工作），紅燈是目前唯一保證有人看到的訊號；3 與閘門失敗的 1
  不同，呼叫端可分辨「資料已上線、只是刪除待放行」與「什麼都沒發」。放行前每次排程都會紅燈，
  這是刻意的。`--dry-run` 只印 `::warning`、exit 0（它本來就不刪）。

憑證：R2_S3_ACCESS_KEY_ID／R2_S3_SECRET_ACCESS_KEY／CLOUDFLARE_ACCOUNT_ID 三者齊備才走 S3。
缺任一回退 wrangler 逐檔 put——**回退路徑不做 listing、不比對、不刪除、沒有線上基準**
（閘門只檢查不為 0），而且全量逐檔非常慢；只留作除錯，CI 不走（#99 起憑證已齊）。

用法：
  python infra/publish.py --bucket ntutbox-cdn --out data --dry-run      # 印上傳／刪除清單
  python infra/publish.py --bucket ntutbox-cdn --out data
  python infra/publish.py --bucket ntutbox-cdn --out data --allow-mass-delete 115-1,standards
  python infra/publish.py --bucket ntutbox-cdn --out data --no-skip-unchanged   # 強制全傳（改 metadata 時）
  python infra/publish.py --bucket ntutbox-cdn --out data --terms 115-1         # 閘門只檢查指定學期
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))
from ntut_catalog.cli import expand_terms  # noqa: E402

_SHORT_CACHE = "public, max-age=300"     # manifest / enrollment（常變）
_LONG_CACHE = "public, max-age=3600"     # catalog / classes / periods / calendar/events（靠 sha + ETag 304）
# 週次表一學期最多修訂一兩次，但**不可宣稱 immutable**——開學前會有修正版。
_CALENDAR_CACHE = "public, max-age=86400, stale-while-revalidate=604800"

TAIPEI = dt.timezone(dt.timedelta(hours=8))
V1_PREFIX = "course/v1/"
MANIFEST_REL = "v1/manifest.json"
DEFAULT_MIN_RATIO = 0.95
MASS_DELETE_RATIO = 0.10

EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_DELETIONS_SKIPPED = 3

_TERM_RE = re.compile(r"^\d{3}-[12]$")


def parse_terms_arg(spec: str) -> List[str]:
    """`--terms` 解析：與 CLI 同一套規則（`a:b` 範圍、逗號混用），格式錯誤丟 ValueError。

    之前只切逗號，dispatch 填 `110-1:115-1` 會被當成單一學期字串傳下去。
    """
    try:
        terms = expand_terms(spec)
    except ValueError as e:
        raise ValueError(f"invalid --terms: {spec!r}") from e
    bad = [t for t in terms if not _TERM_RE.match(t)]
    if not terms or bad:
        raise ValueError(f"invalid --terms: {spec!r}")
    return terms


def r2_key(rel_path: str) -> str:
    """v1 相對路徑 → R2 object key（前綴 course/，對齊 cdn.ntutbox.com/course/v1/）。"""
    return "course/" + rel_path.lstrip("/")


def cache_control_for(rel_path: str) -> str:
    name = rel_path.rsplit("/", 1)[-1]
    if name == "manifest.json" or name == "enrollment.json":
        return _SHORT_CACHE
    if name == "calendar.json":          # terms/{term}/calendar.json（週次表）
        return _CALENDAR_CACHE
    return _LONG_CACHE


def min_ratio_from_env() -> float:
    """repo var `QUALITY_MIN_RATIO` 經 env 注入；未設或空字串 → 0.95。"""
    raw = os.environ.get("QUALITY_MIN_RATIO", "").strip()
    if not raw:
        return DEFAULT_MIN_RATIO
    try:
        return float(raw)
    except ValueError as e:
        raise ValueError(f"invalid QUALITY_MIN_RATIO: {raw!r}") from e


def quality_gate(current: int, previous: int, min_ratio: float) -> Tuple[bool, str]:
    """current=本次課數、previous=基準（0=無基準）。回 (通過?, 原因)。"""
    if current == 0:
        return False, "course count is 0"
    if previous > 0 and current < previous * min_ratio:
        return False, f"course count dropped: {current} < {previous}*{min_ratio:.2f}"
    return True, ""


def _catalog_count(manifest: Optional[dict], term: str) -> Optional[int]:
    try:
        count = manifest["terms"][term]["catalog"].get("count")  # type: ignore[index]
    except (KeyError, TypeError, AttributeError):
        return None
    return count if isinstance(count, int) else None


def check_gate(local: dict, live: Optional[dict], terms: List[str],
               min_ratio: float) -> List[Tuple[str, str]]:
    """對每個學期跑閘門，回傳失敗清單 [(term, 原因)]。

    本次課數取本地 manifest 的 `count`（derive 產出；學期不在本地 → 0 → 擋）。
    基準取線上 manifest 的 `count`；線上沒有 → 0（只檢查不為 0）。
    """
    failures = []
    for t in terms:
        current = _catalog_count(local, t) or 0
        previous = _catalog_count(live, t) or 0
        ok, why = quality_gate(current, previous, min_ratio)
        if not ok:
            failures.append((t, why))
    return failures


# ── 本地 v1 ─────────────────────────────────────────────────────────────

def local_files(out_dir: Path) -> List[str]:
    """本地 v1 全部檔案（`v1/...` 相對路徑，排序）。略過 `.DS_Store` 這類點檔。"""
    v1 = out_dir / "v1"
    if not v1.exists():
        return []
    rels = []
    for p in v1.rglob("*"):
        rel = p.relative_to(out_dir)
        if p.is_file() and not any(part.startswith(".") for part in rel.parts):
            rels.append(rel.as_posix())
    return sorted(rels)


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def unchanged_rels(out_dir: Path, rels: List[str], remote: Dict[str, str]) -> Set[str]:
    """遠端 ETag 與本機內容 MD5 相同 → 這次不必重傳。

    **單一 part 物件的 ETag 就是內容 MD5**（2026-09-20 對 cdn.ntutbox.com 實測）。
    multipart 物件的 ETag 是 `<md5>-<段數>`，不是內容雜湊 → 一律視為不同、照傳。
    """
    skip: Set[str] = set()
    for rel in rels:
        etag = remote.get(r2_key(rel))
        if not etag or "-" in etag:
            continue
        src = out_dir / rel
        if src.is_file() and _md5(src) == etag:
            skip.add(rel)
    return skip


# ── 過期刪除 ─────────────────────────────────────────────────────────────

def deletion_prefix(key: str) -> Optional[str]:
    """R2 key → 它所屬的「可刪 prefix」；不可刪（v1 根目錄、其他目錄、v1 以外）→ None。

    可刪 prefix 以 `course/v1/` 之下的相對路徑表示：`terms/115-1/`、`standards/`、`calendar/`。
    """
    if not key.startswith(V1_PREFIX):
        return None
    parts = key[len(V1_PREFIX):].split("/")
    if len(parts) >= 3 and parts[0] == "terms" and parts[1]:
        return f"terms/{parts[1]}/"
    if len(parts) >= 2 and parts[0] in ("standards", "calendar"):
        return f"{parts[0]}/"
    return None


def normalize_prefix(spec: str) -> str:
    """`--allow-mass-delete` 的值：`115-1`／`terms/115-1`／`standards`／`calendar/` 都接受。"""
    s = spec.strip().strip("/")
    if _TERM_RE.match(s):
        return f"terms/{s}/"
    if re.match(r"^terms/\d{3}-[12]$", s) or s in ("standards", "calendar"):
        return f"{s}/"
    raise ValueError(f"invalid --allow-mass-delete prefix: {spec!r}"
                     "（接受學期如 115-1、terms/115-1、standards、calendar）")


@dataclass
class DeletionPlan:
    delete: Dict[str, List[str]] = field(default_factory=dict)          # prefix → keys（會刪）
    skipped: Dict[str, Tuple[int, int]] = field(default_factory=dict)   # prefix → (待刪, 遠端總數)
    allowed: Set[str] = field(default_factory=set)                      # 超過 10% 但已放行

    @property
    def keys(self) -> List[str]:
        return [k for p in sorted(self.delete) for k in self.delete[p]]


def plan_deletions(local_rels: Iterable[str], remote: Dict[str, str],
                   allow_mass_delete: Set[str] = frozenset()) -> DeletionPlan:
    """R2 有、本地沒有、且落在可刪 prefix 內 → 待刪；每個 prefix 各自套 10% 保險。

    分母是**遠端**該 prefix 的物件數（刪掉的比例是相對於線上現況）。
    """
    local_keys = {r2_key(r) for r in local_rels}
    totals: Dict[str, int] = {}
    stale: Dict[str, List[str]] = {}
    for key in remote:
        prefix = deletion_prefix(key)
        if prefix is None:
            continue
        totals[prefix] = totals.get(prefix, 0) + 1
        if key not in local_keys:
            stale.setdefault(prefix, []).append(key)
    plan = DeletionPlan()
    for prefix, keys in sorted(stale.items()):
        keys.sort()
        if len(keys) > totals[prefix] * MASS_DELETE_RATIO:
            if prefix not in allow_mass_delete:
                plan.skipped[prefix] = (len(keys), totals[prefix])
                continue
            plan.allowed.add(prefix)
        plan.delete[prefix] = keys
    return plan


# ── wrangler 回退（逐檔、無 listing／刪除；除錯用）──────────────────────────
# R2 偶發 500（wrangler 回 code 10001「We encountered an internal error. Please try
# again.」）。實測：crawl details #5（2026-08-16）上傳第 6 個檔案時中招。單檔 PUT 冪等，重試安全。
UPLOAD_ATTEMPTS = 4
UPLOAD_BACKOFF_S = (2, 5, 15)  # 指數退避；長度 = UPLOAD_ATTEMPTS - 1


def wrangler_put(bucket: str, key: str, path: Path, cache_control: str, dry_run: bool) -> None:
    cmd = [
        "wrangler", "r2", "object", "put", f"{bucket}/{key}",
        "--file", str(path),
        "--content-type", "application/json",
        "--cache-control", cache_control,
        "--remote",
    ]
    if dry_run:
        print(f"[dry-run] PUT {bucket}/{key}  ({cache_control})  <- {path}")
        return

    for attempt in range(1, UPLOAD_ATTEMPTS + 1):
        try:
            subprocess.run(cmd, check=True)
            return
        except subprocess.CalledProcessError:
            if attempt == UPLOAD_ATTEMPTS:
                # 耗盡重試 → 往外拋，讓 workflow 紅燈。不可吞掉：半完成的發佈
                # 比明確失敗更難處理（manifest 最後推的原子性設計就是為此）。
                print(f"upload failed after {UPLOAD_ATTEMPTS} attempts: {key}", file=sys.stderr)
                raise
            wait = UPLOAD_BACKOFF_S[attempt - 1]
            print(f"upload attempt {attempt}/{UPLOAD_ATTEMPTS} failed: {key} — retrying in {wait}s",
                  file=sys.stderr)
            time.sleep(wait)


# ── S3（R2 相容 S3 API）────────────────────────────────────────────────
# 為什麼：wrangler 只有單物件 put、每檔約 1.5 秒；aws s3 cp --recursive 預設 10 併發。
# 憑證：R2 API Token 建立時一次給三個值，是**同一組憑證的兩種格式**——
#   Token value        → CLOUDFLARE_API_TOKEN（wrangler 用，Cloudflare 自家 API）
#   Access Key ID      → R2_S3_ACCESS_KEY_ID   ┐ 這兩個給 S3 相容 API（aws-cli）
#   Secret Access Key  → R2_S3_SECRET_ACCESS_KEY ┘
# 對照表見 docs/ARCHITECTURE.md §6。

def s3_available() -> bool:
    return all(os.environ.get(k) for k in
               ("R2_S3_ACCESS_KEY_ID", "R2_S3_SECRET_ACCESS_KEY", "CLOUDFLARE_ACCOUNT_ID"))


def _s3_endpoint() -> str:
    return f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com"


def _aws_env() -> Dict[str, str]:
    env = dict(os.environ)
    env["AWS_ACCESS_KEY_ID"] = os.environ["R2_S3_ACCESS_KEY_ID"]
    env["AWS_SECRET_ACCESS_KEY"] = os.environ["R2_S3_SECRET_ACCESS_KEY"]
    env.setdefault("AWS_DEFAULT_REGION", "auto")
    return env


def _run_aws(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True, env=_aws_env())


def _run_aws_json(cmd: List[str]) -> dict:
    out = subprocess.run(cmd, check=True, env=_aws_env(), capture_output=True, text=True).stdout
    return json.loads(out) if out.strip() else {}


LIST_PAGE_ITEMS = 1000


def list_all(fetch_page: Callable[[Optional[str]], dict]) -> Dict[str, str]:
    """把分頁 listing 走到底：`fetch_page(token)` 回 `{"Contents": [...], "NextToken": ...}`。

    **分頁必須完整**（Review Focus 3）：約 3.3 萬物件、每頁 1000 → 33 頁。漏掉後面的頁，
    第 1001 個以後的物件會被當成「R2 沒有」而全部重傳，也不會進入過期比對。
    逐頁走到沒有 token 為止；token 重複視為 listing 壞掉、直接失敗（不可帶著半份清單去刪）。
    """
    out: Dict[str, str] = {}
    token: Optional[str] = None
    seen: Set[str] = set()
    while True:
        page = fetch_page(token)
        for c in page.get("Contents") or []:
            out[c["Key"]] = c["ETag"].strip('"')
        token = page.get("NextToken") or page.get("NextContinuationToken")
        if not token:
            return out
        if token in seen:
            raise RuntimeError(f"listing pagination loop: token {token!r} repeated")
        seen.add(token)


def remote_etags(bucket: str, endpoint: str, prefix: str = V1_PREFIX) -> Dict[str, str]:
    """列出 R2 `course/v1/` 下全部物件的 key → ETag。

    明確分頁（`--max-items` + `--starting-token`，回應帶 `NextToken`）而非依賴 aws-cli 的
    隱式自動分頁——分頁邏輯才能在測試裡用假 client 釘住。
    """
    def fetch_page(token: Optional[str]) -> dict:
        cmd = ["aws", "s3api", "list-objects-v2", "--bucket", bucket, "--prefix", prefix,
               "--endpoint-url", endpoint, "--output", "json",
               "--max-items", str(LIST_PAGE_ITEMS)]
        if token:
            cmd += ["--starting-token", token]
        return _run_aws_json(cmd)
    return list_all(fetch_page)


def fetch_live_manifest(bucket: str, endpoint: str) -> Optional[dict]:
    """S3 GetObject 直讀線上 manifest（不走 CDN）。不存在 → None；其他錯誤 → 往外拋。"""
    with tempfile.TemporaryDirectory() as d:
        dst = Path(d) / "manifest.json"
        proc = subprocess.run(
            ["aws", "s3api", "get-object", "--bucket", bucket, "--key", r2_key(MANIFEST_REL),
             "--endpoint-url", endpoint, str(dst)],
            env=_aws_env(), capture_output=True, text=True)
        if proc.returncode != 0:
            if "NoSuchKey" in proc.stderr or "Not Found" in proc.stderr:
                return None
            raise RuntimeError(f"GetObject {r2_key(MANIFEST_REL)} failed: {proc.stderr.strip()}")
        return json.loads(dst.read_text(encoding="utf-8"))


def _dir_upload_cmds(bucket: str, out_dir: Path, rels: List[str],
                     cache_control: str, endpoint: str) -> List[List[str]]:
    """依「所在目錄」分批，每個目錄一條 aws 指令，來源 scope 到該目錄。

    為什麼不是「單一指令 + 逐檔 --include」（2026-09-20 之前的作法）：awscli 對
    走訪到的每個檔都要把全部 pattern 跑一遍，成本是 O(走訪檔數 × pattern 數)；
    實測 11 學期 32,623 個物件約 10.7 億次比對、推算 68 小時（run 35525476205）。
    scope 到目錄之後，「走訪範圍」就是「要傳的範圍」。
    """
    by_dir: Dict[str, List[str]] = {}
    for rel in rels:
        d, _, name = rel.rpartition("/")
        by_dir.setdefault(d, []).append(name)

    cmds: List[List[str]] = []
    for d, names in sorted(by_dir.items()):
        src = out_dir / d
        cmd = ["aws", "s3", "cp", str(src), f"s3://{bucket}/{r2_key(d)}/",
               "--endpoint-url", endpoint, "--recursive",
               "--content-type", "application/json",
               "--cache-control", cache_control,
               "--only-show-errors"]
        # 裸 --recursive 只在「這個目錄就是整批、且沒有子目錄」時才安全：
        # v1/terms/{t}/ 底下有 course/，不排除的話會把沒變的詳情一起掃上去。
        entries = list(src.iterdir()) if src.is_dir() else []
        on_disk = {e.name for e in entries if e.is_file()}
        has_subdir = any(e.is_dir() for e in entries)
        if has_subdir or set(names) != on_disk:
            cmd += ["--exclude", "*"]
            for name in sorted(names):
                cmd += ["--include", name]
        cmds.append(cmd)
    return cmds


def s3_upload(bucket: str, out_dir: Path, body: List[str], manifest_src: Optional[Path]) -> None:
    """上傳 body（依 Cache-Control 分組、逐目錄），manifest 最後推（原子性）。

    aws s3 cp --recursive 對整批只能下同一個 metadata，所以依 cache-control 分組。
    """
    endpoint = _s3_endpoint()
    groups: Dict[str, List[str]] = {}
    for rel in body:
        groups.setdefault(cache_control_for(rel), []).append(rel)
    for cache_control, rels in groups.items():
        for cmd in _dir_upload_cmds(bucket, out_dir, rels, cache_control, endpoint):
            _run_aws(cmd)
    if manifest_src is not None:
        _run_aws(["aws", "s3", "cp", str(manifest_src), f"s3://{bucket}/{r2_key(MANIFEST_REL)}",
                  "--endpoint-url", endpoint,
                  "--content-type", "application/json",
                  "--cache-control", cache_control_for(MANIFEST_REL),
                  "--only-show-errors"])


DELETE_BATCH = 1000  # S3 DeleteObjects 單次上限


def s3_delete(bucket: str, keys: List[str]) -> None:
    endpoint = _s3_endpoint()
    for i in range(0, len(keys), DELETE_BATCH):
        batch = keys[i:i + DELETE_BATCH]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"Objects": [{"Key": k} for k in batch], "Quiet": True}, f)
            path = f.name
        try:
            _run_aws(["aws", "s3api", "delete-objects", "--bucket", bucket,
                      "--delete", f"file://{path}", "--endpoint-url", endpoint])
        finally:
            os.unlink(path)


# ── manifest 時間戳 ─────────────────────────────────────────────────────

def now_iso() -> str:
    return dt.datetime.now(TAIPEI).isoformat(timespec="seconds")


def stamped_manifest(out_dir: Path, published_at: str, dst: Path) -> Path:
    """把 `published_at` = `generated_at` = 發佈時間寫進 manifest 的**副本**。

    不改 `v1/manifest.json` 本身：v1 是 derive 的確定性產物，publish 只在上傳那一份蓋時間。
    序列化沿用 pydantic model_dump_json 的緊湊格式、保留鍵序。
    """
    data = json.loads((out_dir / MANIFEST_REL).read_text(encoding="utf-8"))
    data["generated_at"] = published_at
    data["published_at"] = published_at
    dst.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return dst


# ── run summary ────────────────────────────────────────────────────────

SUMMARY_LIST_LIMIT = 200


def _bullets(items: List[str], limit: int = SUMMARY_LIST_LIMIT) -> List[str]:
    lines = [f"- `{x}`" for x in items[:limit]]
    if len(items) > limit:
        lines.append(f"- …另 {len(items) - limit} 個")
    return lines


def render_summary(*, bucket: str, dry_run: bool, via: str, uploads: List[str], unchanged: int,
                   deletions: Optional[DeletionPlan], published_at: str) -> str:
    lines = ["## publish v1" + (" (dry-run)" if dry_run else ""), "",
             f"- bucket：`{bucket}`（{via}）",
             f"- published_at：`{published_at}`",
             f"- 上傳：{len(uploads)} 個（另 {unchanged} 個 MD5 相同跳過；manifest 永遠上傳）"]
    if deletions is None:
        lines.append("- 過期刪除：未執行（wrangler 回退路徑沒有 listing）")
    else:
        lines.append(f"- 過期刪除：{len(deletions.keys)} 個")
        if deletions.skipped:
            lines += ["", "### ⚠️ 刪除保險觸發：以下 prefix 的刪除已跳過（上傳照常）", "",
                      "| prefix | 待刪 | 遠端物件數 |", "|---|---|---|"]
            for p, (n, total) in sorted(deletions.skipped.items()):
                lines.append(f"| `{p}` | {n} | {total} |")
            lines += ["", "確認無誤後以 `--allow-mass-delete <prefix>` 重跑放行"
                      "（publish-v1 workflow 的 `allow_mass_delete` 輸入）。"
                      "先用 dry-run 看完整待刪清單。"]
        if deletions.allowed:
            lines.append("- 已放行的大量刪除：" + ", ".join(f"`{p}`" for p in sorted(deletions.allowed)))
        for p in sorted(deletions.delete):
            lines += ["", f"<details><summary>刪除 {p}（{len(deletions.delete[p])}）</summary>", ""]
            lines += _bullets(deletions.delete[p])
            lines += ["", "</details>"]
    lines += ["", f"<details><summary>上傳清單（{len(uploads)}）</summary>", ""]
    lines += _bullets(uploads)
    lines += ["", "</details>", ""]
    return "\n".join(lines)


def _append_env_file(var: str, text: str) -> None:
    path = os.environ.get(var)
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)


# ── main ───────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="publish")
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--out", default="data", help="資料根目錄（含 derive 產出的 v1/）")
    ap.add_argument("--terms", help="品質閘門只檢查這些學期（預設＝本地 manifest 全部學期）；支援 a:b 範圍")
    ap.add_argument("--dry-run", action="store_true", help="只印上傳／刪除清單，不動 R2")
    ap.add_argument("--no-skip-unchanged", action="store_true",
                    help="不做 MD5 差異比對，全部重傳（改 Cache-Control 等 metadata 變更時用）")
    ap.add_argument("--allow-mass-delete", action="append", default=[], metavar="PREFIX",
                    help="放行單一 prefix 超過 10%% 的刪除：115-1／terms/115-1／standards／calendar"
                         "（可重複、可逗號分隔）")
    ap.add_argument("--no-s3", action="store_true", help="強制走 wrangler 逐檔（除錯用；不比對、不刪除）")
    args = ap.parse_args(argv)

    out_dir = Path(args.out).resolve()
    try:
        allow = {normalize_prefix(p) for spec in args.allow_mass_delete
                 for p in spec.split(",") if p.strip()}
        min_ratio = min_ratio_from_env()
        gate_terms = parse_terms_arg(args.terms) if args.terms else None
    except ValueError as e:
        ap.error(str(e))

    manifest_path = out_dir / MANIFEST_REL
    if not manifest_path.exists():
        print(f"❌ {manifest_path} 不存在——先跑 `python -m ntut_catalog derive --out {args.out}`",
              file=sys.stderr)
        return EXIT_GATE_FAILED
    local_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    use_s3 = s3_available() and not args.no_s3
    endpoint = _s3_endpoint() if use_s3 else ""

    # 1. 品質閘門（基準：線上 manifest）
    live: Optional[dict] = None
    if use_s3:
        live = fetch_live_manifest(args.bucket, endpoint)
        if live is None:
            print("線上尚無 manifest → 閘門只檢查課數不為 0")
    else:
        print("⚠️  無 S3 憑證 → 讀不到線上 manifest，閘門只檢查課數不為 0", file=sys.stderr)
    terms = gate_terms if gate_terms is not None else sorted(local_manifest.get("terms", {}))
    failures = check_gate(local_manifest, live, terms, min_ratio)
    if failures:
        for t, why in failures:
            print(f"❌ quality gate FAILED for {t}: {why} — 不發佈", file=sys.stderr)
        _append_env_file("GITHUB_STEP_SUMMARY", "## publish v1\n\n❌ 品質閘門未通過，未上傳任何物件：\n\n"
                         + "\n".join(f"- `{t}`：{why}" for t, why in failures) + "\n")
        return EXIT_GATE_FAILED

    # 2. 全量比對
    files = local_files(out_dir)
    body = [f for f in files if f != MANIFEST_REL]
    published_at = now_iso()
    deletions: Optional[DeletionPlan] = None
    unchanged = 0
    if use_s3:
        remote = remote_etags(args.bucket, endpoint)
        print(f"remote: {len(remote)} object(s) under {V1_PREFIX}; local: {len(files)} file(s)")
        if not args.no_skip_unchanged:
            skip = unchanged_rels(out_dir, body, remote)
            unchanged = len(skip)
            body = [f for f in body if f not in skip]
        deletions = plan_deletions(files, remote, allow)
    uploads = body + [MANIFEST_REL]
    _append_env_file("GITHUB_STEP_SUMMARY", render_summary(
        bucket=args.bucket, dry_run=args.dry_run, via="s3" if use_s3 else "wrangler",
        uploads=uploads, unchanged=unchanged, deletions=deletions, published_at=published_at))

    # 3. 上傳（body → manifest）；4. 刪除（manifest 之後）
    if args.dry_run:
        for rel in uploads:
            print(f"[dry-run] PUT {args.bucket}/{r2_key(rel)}  ({cache_control_for(rel)})")
        for key in deletions.keys if deletions else []:
            print(f"[dry-run] DELETE {args.bucket}/{key}")
    else:
        with tempfile.TemporaryDirectory() as d:
            manifest_src = stamped_manifest(out_dir, published_at, Path(d) / "manifest.json")
            if use_s3:
                print(f"uploading {len(uploads)} object(s) via S3 (skipped {unchanged} unchanged)")
                s3_upload(args.bucket, out_dir, body, manifest_src)
                if deletions and deletions.keys:
                    print(f"deleting {len(deletions.keys)} stale object(s)")
                    s3_delete(args.bucket, deletions.keys)
            else:
                print(f"⚠️  S3 憑證未設定，回退 wrangler 逐檔上傳 {len(uploads)} 個物件"
                      "（不比對、不刪除；約每檔 1.5 秒）", file=sys.stderr)
                for rel in body:
                    wrangler_put(args.bucket, r2_key(rel), out_dir / rel, cache_control_for(rel), False)
                wrangler_put(args.bucket, r2_key(MANIFEST_REL), manifest_src,
                             cache_control_for(MANIFEST_REL), False)

    n_del = len(deletions.keys) if deletions else 0
    print(f"{'[dry-run] ' if args.dry_run else ''}published {len(uploads)} object(s), "
          f"deleted {n_del}, skipped {unchanged} unchanged, to {args.bucket} "
          f"via {'s3' if use_s3 else 'wrangler'}")

    skipped = deletions.skipped if deletions else {}
    _append_env_file("GITHUB_OUTPUT", f"deletions_skipped={','.join(sorted(skipped))}\n")
    if skipped:
        level = "warning" if args.dry_run else "error"
        for p, (n, total) in sorted(skipped.items()):
            print(f"::{level} title=R2 刪除保險觸發::{p} 待刪 {n}/{total}（> 10%），已跳過刪除；"
                  f"其餘照常上線。確認後以 --allow-mass-delete {p} 放行")
        if not args.dry_run:
            return EXIT_DELETIONS_SKIPPED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
