"""發佈 v1 到 Cloudflare R2（wrangler）：build-v1 → quality gate → 原子上傳。

策略（spec Phase B）：
  - 從 canonical 重建【完整】v1（manifest 涵蓋全學期）
  - quality gate：課數驟降 / 0 課 → 不發佈
  - 逐檔 wrangler r2 object put；term files 全成功後，manifest 最後推（原子性）
  - 不預壓縮（CF 邊緣自動壓）；per-object Cache-Control；key 前綴 course/

用法：
  python infra/publish.py --bucket ntutbox-cdn --terms 115-1 [--previous-counts '{"115-1":2450}']
  python infra/publish.py --bucket ntutbox-cdn --all
  python infra/publish.py --bucket ntutbox-cdn --terms 115-1 --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# publish 需要重建 v1（從 canonical），故依賴 crawler 套件
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))
from ntut_catalog.artifacts import build_v1  # noqa: E402

_SHORT_CACHE = "public, max-age=300"     # manifest / enrollment（常變）
_LONG_CACHE = "public, max-age=3600"     # catalog / classes / periods（靠 sha + ETag 304）


def r2_key(rel_path: str) -> str:
    """v1 相對路徑 → R2 object key（前綴 course/，對齊 cdn.ntutbox.com/course/v1/）。"""
    return "course/" + rel_path.lstrip("/")


def cache_control_for(rel_path: str) -> str:
    name = rel_path.rsplit("/", 1)[-1]
    if name == "manifest.json" or name == "enrollment.json":
        return _SHORT_CACHE
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
        for name in ["catalog.json", "classes.json", "periods.json", "enrollment.json", "mprograms.json"]:
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
    files.append("v1/manifest.json")
    return files


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
    subprocess.run(cmd, check=True)


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
    for rel in plan_uploads(files):
        wrangler_put(args.bucket, r2_key(rel), out_dir / rel, cache_control_for(rel), args.dry_run)

    print(f"{'[dry-run] ' if args.dry_run else ''}published {len(files)} object(s) to {args.bucket}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
