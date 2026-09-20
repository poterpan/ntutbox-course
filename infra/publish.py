"""發佈 v1 到 Cloudflare R2（wrangler）：build-v1 → quality gate → 原子上傳。

策略（spec Phase B）：
  - 從 canonical 重建【完整】v1（manifest 涵蓋全學期）
  - quality gate：課數驟降 / 0 課 → 不發佈
  - S3 批次上傳（逐目錄 scope）；缺憑證回退 wrangler 逐檔 put
  - 差異上傳：遠端 ETag(=內容 MD5) 與本機相同就跳過；manifest 不跳過、永遠最後推（原子性）
  - 不預壓縮（CF 邊緣自動壓）；per-object Cache-Control；key 前綴 course/

用法：
  python infra/publish.py --bucket ntutbox-cdn --terms 115-1 [--previous-counts '{"115-1":2450}']
  python infra/publish.py --bucket ntutbox-cdn --all
  python infra/publish.py --bucket ntutbox-cdn --terms 115-1 --dry-run
  python infra/publish.py --bucket ntutbox-cdn --all --no-skip-unchanged   # 強制全傳
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# publish 需要重建 v1（從 canonical），故依賴 crawler 套件
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))
from ntut_catalog.artifacts import build_v1  # noqa: E402

_SHORT_CACHE = "public, max-age=300"     # manifest / enrollment（常變）
_LONG_CACHE = "public, max-age=3600"     # catalog / classes / periods / calendar/events（靠 sha + ETag 304）
# 週次表一學期最多修訂一兩次，但**不可宣稱 immutable**——開學前會有修正版。
_CALENDAR_CACHE = "public, max-age=86400, stale-while-revalidate=604800"


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


def quality_gate(current: int, previous: int, min_ratio: float) -> Tuple[bool, str]:
    """current=本次課數、previous=上次（0=無基準）。回 (通過?, 原因)。"""
    if current == 0:
        return False, "course count is 0"
    if previous > 0 and current < previous * min_ratio:
        return False, f"course count dropped: {current} < {previous}*{min_ratio:.2f}"
    return True, ""


def plan_uploads(files: List[str]) -> List[str]:
    """排上傳順序：term files 先、manifest 最後（client 看到 manifest 時物件已就緒）。"""
    terms = [f for f in files if not f.endswith("manifest.json")]
    manifest = [f for f in files if f.endswith("manifest.json")]
    return terms + manifest


def _term_count(out_dir: Path, term: str) -> int:
    nd = out_dir / "canonical" / term / "catalog.ndjson"
    if not nd.exists():
        return 0
    return sum(1 for line in nd.read_text(encoding="utf-8").splitlines() if line.strip())


def _v1_files_for(out_dir: Path, terms: Optional[List[str]], include_details: bool = False) -> List[str]:
    """要上傳的 v1 相對路徑。預設：每學期 bulk 檔 + standards + manifest。
    詳情(course/{id}.json) 數量龐大(~1500/學期)，預設不傳；--include-details 才傳。"""
    v1 = out_dir / "v1"
    files: List[str] = []
    term_dirs = (
        [v1 / "terms" / t for t in terms] if terms
        else sorted(p for p in (v1 / "terms").iterdir() if p.is_dir()) if (v1 / "terms").exists() else []
    )
    for td in term_dirs:
        for name in ["catalog.json", "classes.json", "periods.json", "enrollment.json",
                     "mprograms.json", "names.json"]:
            p = td / name
            if p.exists():
                files.append(str(p.relative_to(out_dir)))
        if include_details and (td / "course").exists():
            for cf in sorted((td / "course").glob("*.json")):
                files.append(str(cf.relative_to(out_dir)))
    # 課程標準（跨入學年，top-level）
    std_dir = v1 / "standards"
    if std_dir.exists():
        for sf in sorted(std_dir.glob("*.json")):
            files.append(str(sf.relative_to(out_dir)))
    # 週次表**不吃 --terms**：它只需要行事曆，不需要課程目錄，所以下學期的週次表
    # 往往早於課程目錄就能產（#168 要的正是提前拿到）。綁 --terms 的話，115-2 的
    # 週次表會一直停在本機、永遠不上線——App 端 2026-09-19 實測 404 就是這個原因。
    # 有產出就發佈，範圍由 crawl-calendar 的推導決定，不需要任何人手動設定。
    all_terms_dir = v1 / "terms"
    if all_terms_dir.exists():
        for cal in sorted(all_terms_dir.glob("*/calendar.json")):
            rel = str(cal.relative_to(out_dir))
            if rel not in files:
                files.append(rel)
    # 行事曆事件 feed（跨學期，top-level）。Cache-Control 走預設 _LONG_CACHE(3600)：
    # 每日重抓，颱風假／補課這種臨時異動要快到使用者手上，不宜比 1 小時更久。
    cal_dir = v1 / "calendar"
    if cal_dir.exists():
        for cf in sorted(cal_dir.glob("*.json")):
            files.append(str(cf.relative_to(out_dir)))
    files.append("v1/manifest.json")
    return files


# R2 偶發 500（wrangler 回 code 10001「We encountered an internal error. Please try
# again.」）。實測：crawl details #5（2026-08-16）上傳第 6 個檔案時中招，前 5 個已上傳、
# 整個 workflow 掛掉。單檔上傳是冪等的 PUT，重試安全。
# backfill 要上傳 11 學期 ×（6 檔 + 約 21,500 個 course/*.json），不重試幾乎必然踩到。
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



# ── S3 批次上傳（R2 相容 S3 API）────────────────────────────────
# 為什麼需要：wrangler 只有單物件 put、每檔約 1.5 秒（每次重啟進程）。
# backfill 11 學期要傳約 26,840 個 course/*.json → 逐檔約 9 小時，超過
# GitHub runner 6 小時上限，而且 26,840 次獨立呼叫撞到 R2 偶發 500 的
# 機率極高（實測 crawl details #5 就是這樣掛的）。
# aws s3 cp --recursive 預設 10 併發，同一批只付一次認證與進程成本。
#
# 憑證：R2 API Token 建立時一次給三個值，是**同一組憑證的兩種格式**——
#   Token value        → CLOUDFLARE_API_TOKEN（wrangler 用，Cloudflare 自家 API）
#   Access Key ID      → R2_S3_ACCESS_KEY_ID   ┐ 這兩個給 S3 相容 API（aws-cli）
#   Secret Access Key  → R2_S3_SECRET_ACCESS_KEY ┘
# 所以一組 token 就能同時餵飽兩條路徑，不需要維護兩組。
# R2_S3_* 與 CLOUDFLARE_ACCOUNT_ID 三者齊備才啟用 S3；缺任一回退 wrangler（行為不變）。
# 對照表見 docs/ARCHITECTURE.md §6。

def s3_available() -> bool:
    return all(os.environ.get(k) for k in
               ("R2_S3_ACCESS_KEY_ID", "R2_S3_SECRET_ACCESS_KEY", "CLOUDFLARE_ACCOUNT_ID"))


def _s3_endpoint() -> str:
    return f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com"


def _run_aws(cmd: List[str]) -> None:
    env = dict(os.environ)
    env["AWS_ACCESS_KEY_ID"] = os.environ["R2_S3_ACCESS_KEY_ID"]
    env["AWS_SECRET_ACCESS_KEY"] = os.environ["R2_S3_SECRET_ACCESS_KEY"]
    env.setdefault("AWS_DEFAULT_REGION", "auto")
    subprocess.run(cmd, check=True, env=env)


def _run_aws_json(cmd: List[str]) -> dict:
    env = dict(os.environ)
    env["AWS_ACCESS_KEY_ID"] = os.environ["R2_S3_ACCESS_KEY_ID"]
    env["AWS_SECRET_ACCESS_KEY"] = os.environ["R2_S3_SECRET_ACCESS_KEY"]
    env.setdefault("AWS_DEFAULT_REGION", "auto")
    out = subprocess.run(cmd, check=True, env=env, capture_output=True, text=True).stdout
    return json.loads(out) if out.strip() else {}


def remote_etags(bucket: str, endpoint: str, prefix: str = "course/") -> Dict[str, str]:
    """列出 R2 既有物件的 key → ETag。aws-cli 會自動分頁（32k 物件約 33 次請求）。

    **單一 part 物件的 ETag 就是內容 MD5**——2026-09-20 對
    `cdn.ntutbox.com/course/v1/terms/115-1/course/360748.json` 實測：
    ETag 與 body 的 MD5 皆為 bf5fb00509ba47a2efbdfe60d9193cda。
    （交接文件 §6 原本把這件事記為「未實測」，現已驗證。）
    """
    data = _run_aws_json(["aws", "s3api", "list-objects-v2", "--bucket", bucket,
                          "--prefix", prefix, "--endpoint-url", endpoint, "--output", "json"])
    return {c["Key"]: c["ETag"].strip('"') for c in data.get("Contents", [])}


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def unchanged_rels(out_dir: Path, rels: List[str], remote: Dict[str, str]) -> Set[str]:
    """遠端 ETag 與本機內容 MD5 相同 → 這次不必重傳。

    為什麼划算：#89／#95 已經讓「內容沒變的產物 byte-identical」，所以每週
    `crawl-details` 重傳的 2,700 個檔裡，真正變動的通常只有少數幾十個。

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


def _dir_upload_cmds(bucket: str, out_dir: Path, rels: List[str],
                     cache_control: str, endpoint: str) -> List[List[str]]:
    """依「所在目錄」分批，每個目錄一條 aws 指令，來源 scope 到該目錄。

    為什麼不是「單一指令 + 逐檔 --include」（2026-09-20 之前的作法）：awscli 對
    走訪到的每個檔都要把全部 pattern 跑一遍（後面的 pattern 能覆蓋前面的，不能
    提早跳出），成本是 O(走訪檔數 × pattern 數)。而來源是整個 out_dir，所以
    「只發一個學期」也要走訪全部 11 學期的產物。

    實測（2026-09-20，run 35525476205）：11 學期 32,623 個物件 → 約 10.7 億次
    比對，8 檔/分、推算 68 小時。比它當初取代的 wrangler 逐檔（約 9 小時）還慢
    7 倍，等於優化在它唯一的目標情境上是負的。

    scope 到目錄之後，「走訪範圍」就是「要傳的範圍」：整個目錄都要傳時 pattern
    數是 0，只傳一部分時也只需要該目錄內那幾個檔名。
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
        # v1/terms/{t}/ 底下有 course/，不排除的話會把詳情一起掃上去，
        # 等於 --include-details 失效。
        entries = list(src.iterdir()) if src.is_dir() else []
        on_disk = {e.name for e in entries if e.is_file()}
        has_subdir = any(e.is_dir() for e in entries)
        if has_subdir or set(names) != on_disk:
            cmd += ["--exclude", "*"]
            for name in sorted(names):
                cmd += ["--include", name]
        cmds.append(cmd)
    return cmds


def s3_sync_upload(bucket: str, out_dir: Path, files: List[str], dry_run: bool,
                   skip_unchanged: bool = True) -> None:
    """批次上傳，保留兩個既有保證：
       ① 原子性——manifest 最後推（client 看到 manifest 時物件已就緒）
       ② per-object Cache-Control——manifest/enrollment 短快取、其餘長快取

       aws s3 cp --recursive 對整批只能下同一個 metadata，所以依 cache-control
       分組；manifest 單獨最後一批。
    """
    if dry_run:
        for rel in plan_uploads(files):
            print(f"[dry-run][s3] PUT {bucket}/{r2_key(rel)}  ({cache_control_for(rel)})")
        return

    ordered = plan_uploads(files)           # term files 先、manifest 最後
    manifest = [f for f in ordered if f.endswith("manifest.json")]
    body = [f for f in ordered if not f.endswith("manifest.json")]

    # manifest 不參與跳過：它是「物件都就緒了」的信號，永遠要推。
    if skip_unchanged and body:
        skip = unchanged_rels(out_dir, body, remote_etags(bucket, _s3_endpoint()))
        if skip:
            print(f"skipping {len(skip)} unchanged object(s); uploading {len(body) - len(skip)}")
            body = [f for f in body if f not in skip]

    groups: Dict[str, List[str]] = {}
    for rel in body:
        groups.setdefault(cache_control_for(rel), []).append(rel)

    endpoint = _s3_endpoint()
    for cache_control, rels in groups.items():
        for cmd in _dir_upload_cmds(bucket, out_dir, rels, cache_control, endpoint):
            _run_aws(cmd)

    for rel in manifest:                    # 最後推，維持原子性
        _run_aws(["aws", "s3", "cp", str(out_dir / rel), f"s3://{bucket}/{r2_key(rel)}",
                  "--endpoint-url", endpoint,
                  "--content-type", "application/json",
                  "--cache-control", cache_control_for(rel),
                  "--only-show-errors"])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="publish")
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--out", default="data", help="資料根目錄（含 canonical/、v1/）")
    ap.add_argument("--terms", help="逗號分隔；省略時配 --all")
    ap.add_argument("--all", action="store_true", help="發佈全部學期")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-ratio", type=float, default=0.95)
    ap.add_argument("--previous-counts", default="{}", help='JSON {"115-1": 2450}（上次課數基準）')
    ap.add_argument("--generated-at", default="", help="manifest generated_at（省略用佔位）")
    ap.add_argument("--include-details", action="store_true", help="也上傳 course/{id}.json 詳情（量大、慢）")
    ap.add_argument("--no-s3", action="store_true", help="強制走 wrangler 逐檔（除錯用）")
    ap.add_argument("--no-skip-unchanged", action="store_true",
                    help="不做 ETag 差異比對，全部重傳（改 Cache-Control 等 metadata 變更時用）")
    args = ap.parse_args(argv)

    out_dir = Path(args.out).resolve()
    terms = None if args.all else ([t.strip() for t in args.terms.split(",")] if args.terms else None)
    if terms is None and not args.all:
        ap.error("need --terms or --all")

    # 1. 重建完整 v1（manifest 涵蓋全學期，不只本次）
    build_v1(out_dir, args.generated_at or "1970-01-01T00:00:00+08:00")

    # 2. quality gate（對要發佈的學期）
    previous = json.loads(args.previous_counts)
    gate_terms = terms if terms else (
        [p.name for p in sorted((out_dir / "v1" / "terms").iterdir()) if p.is_dir()]
        if (out_dir / "v1" / "terms").exists() else []
    )
    for t in gate_terms:
        ok, why = quality_gate(_term_count(out_dir, t), int(previous.get(t, 0)), args.min_ratio)
        if not ok:
            print(f"❌ quality gate FAILED for {t}: {why} — 不發佈", file=sys.stderr)
            return 1

    # 3. 原子上傳：term files 先、manifest 最後
    files = _v1_files_for(out_dir, terms, include_details=args.include_details)
    use_s3 = s3_available() and not args.no_s3
    if use_s3:
        print(f"uploading {len(files)} object(s) via S3 batch (aws s3 cp --recursive)")
        s3_sync_upload(args.bucket, out_dir, files, args.dry_run,
                       skip_unchanged=not args.no_skip_unchanged)
    else:
        if args.include_details and not args.no_s3:
            print("⚠️  S3 credentials 未設定，回退 wrangler 逐檔上傳——"
                  f"{len(files)} 個物件會很慢（約 {len(files) * 1.5 / 60:.0f} 分）。"
                  "設定 R2_S3_* 可大幅加速。", file=sys.stderr)
        for rel in plan_uploads(files):
            wrangler_put(args.bucket, r2_key(rel), out_dir / rel, cache_control_for(rel), args.dry_run)

    print(f"{'[dry-run] ' if args.dry_run else ''}published {len(files)} object(s) to {args.bucket}"
          f" via {'s3' if use_s3 else 'wrangler'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
