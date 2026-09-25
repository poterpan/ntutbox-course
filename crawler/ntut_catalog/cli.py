"""CLI：
  python -m ntut_catalog pipeline --cadence daily [--datasets a,b] [--terms …] --out ../data   # fetch（只寫 canonical＋stage）
  python -m ntut_catalog merge    --stage ../data/stage --out ../data                          # stage → 最新 canonical（上鎖 job）
  python -m ntut_catalog derive   --out ../data                                                # canonical → v1（唯一入口）
  python -m ntut_catalog migrate-pipeline-v2 --data ../data/canonical                          # 一次性遷移（spec §7，切換後刪除）

三層邊界（spec §1）：fetch 只寫 canonical、derive 只產 v1／reports、publish（infra/publish.py）只上傳。
資料集宣告在 `registry.py`；新增資料集不必新增子命令或 workflow。

2026-09 管線重構移除：一次性指令 `migrate`／`rederive`／`rematric`／`recategorize`／
`migrate-details`／`reprocess-progress`（逐週進度改在 derive 即時計算），以及各資料集
各自一支的 `crawl`／`crawl-detail`／`crawl-mprograms`／`crawl-standards`／`crawl-calendar`／
`refresh-enrollment`——全部改走 `pipeline --datasets …`（本機一次做完可加 `--merge`）。

term 範圍只展開 sem 1/2（暑期 3 不在 P0 範圍）。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

from ntut_catalog.artifacts import derive
from ntut_catalog.client import CatalogClient, detect_current_term
from ntut_catalog.orchestrator import parse_term_key

logger = logging.getLogger("ntut_catalog")

TAIPEI = timezone(timedelta(hours=8))


def expand_terms(spec: str) -> List[str]:
    """'110-1:115-1' → [110-1, 110-2, ..., 115-1]；'114-1' → [114-1]；逗號分隔可混用。"""
    out: List[str] = []
    for part in spec.split(","):
        part = part.strip()
        if ":" not in part:
            out.append(part)
            continue
        start_s, end_s = part.split(":")
        y, s = parse_term_key(start_s)
        ey, es = parse_term_key(end_s)
        while (y, s) <= (ey, es):
            out.append(f"{y}-{s}")
            s += 1
            if s > 2:
                y, s = y + 1, 1
    return out


def term_already_done(out_dir: Path, term: str) -> bool:
    """resume/skip 判斷：看 canonical（真相），非 v1（衍生物）。"""
    return (out_dir / "canonical" / term / "catalog.ndjson").exists()


def _setup_logging(out_dir: Path, prefix: str) -> None:
    ts = datetime.now(TAIPEI).strftime("%Y%m%d-%H%M%S")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr),
                  logging.FileHandler(out_dir / f"{prefix}-log-{ts}.txt", encoding="utf-8")],
    )


def _split(raw: str | None) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else []


def _cmd_pipeline(args, out_dir: Path) -> int:
    from ntut_catalog.merge import merge_fetch_output
    from ntut_catalog.pipeline import UsageError, run

    stage = Path(args.stage).resolve() if args.stage else out_dir / "stage"
    try:
        terms = expand_terms(args.terms) if args.terms else []
    except ValueError:
        print(f"invalid --terms: {args.terms!r}", file=sys.stderr)
        return 2
    try:
        result = run(args.cadence, _split(args.datasets), terms, out_dir, stage)
    except UsageError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    failed = [f"{e['name']}:{e['term'] or '_global'}" for e in result.datasets if not e["ok"]]
    logger.info("pipeline %s done: %d ok, failed: %s", args.cadence,
                len(result.datasets) - len(failed), failed or "none")
    if args.merge:
        report = merge_fetch_output(stage, out_dir)
        print(json.dumps(report.to_json(), ensure_ascii=False, indent=1))
    return 1 if failed else 0


def _cmd_merge(args, out_dir: Path) -> int:
    from ntut_catalog.merge import merge_fetch_output

    stage = Path(args.stage).resolve()
    report = merge_fetch_output(stage, out_dir)
    text = json.dumps(report.to_json(), ensure_ascii=False, indent=1) + "\n"
    report_path = Path(args.report).resolve() if args.report else stage / "merge-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ntut_catalog")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("current-term", help="偵測學校當前學期並印出（如 115-1）")
    pl = sub.add_parser("pipeline",
                        help="依 cadence 跑登錄表的資料集（fetch job）：寫 canonical＋stage/pipeline-result.json")
    pl.add_argument("--cadence", required=True, choices=["daily", "weekly", "season", "manual"])
    pl.add_argument("--datasets", default=None,
                    help="只跑這些資料集（逗號分隔；預設＝該 cadence 全部，可跨 cadence 供補爬）")
    pl.add_argument("--terms", default=None,
                    help="覆寫學期規則，如 115-1 或 110-1:114-2（season 必填）")
    pl.add_argument("--out", default="../data", help="資料根目錄（含 canonical/；預設 ../data）")
    pl.add_argument("--stage", default=None, help="交給 merge 的輸出目錄（預設 <out>/stage）")
    pl.add_argument("--merge", action="store_true",
                    help="跑完直接 merge 回 <out>（本機一次做完用；CI 由上鎖 job 另跑 merge）")
    mg = sub.add_parser("merge", help="把 pipeline 的 stage 合併進最新 canonical（commit-publish job）")
    mg.add_argument("--stage", required=True, help="pipeline 的 stage 目錄（含 pipeline-result.json）")
    mg.add_argument("--out", default="../data", help="資料根目錄（最新 data branch 在 <out>/canonical）")
    mg.add_argument("--report", default=None, help="MergeReport JSON 輸出路徑（預設 <stage>/merge-report.json）")
    dv = sub.add_parser("derive",
                        help="canonical → v1（全量、確定性；先清空 v1/）。publish 前必跑")
    dv.add_argument("--out", default="../data", help="資料根目錄（含 canonical/；預設 ../data）")
    mv = sub.add_parser("migrate-pipeline-v2",
                        help="一次性：舊 canonical → 管線 v2 形狀（spec §7；冪等，切換後刪除）")
    mv.add_argument("--data", required=True,
                    help="data branch checkout（canonical 根目錄，須為 git 工作區）")
    ps = sub.add_parser("pua-scan",
                        help="監測新造字(PUA)碼位：canonical 出現 PUA_MAP 未收錄碼位 → 列出並 exit 1")
    ps.add_argument("--terms", required=True, help="學期，如 115-1（可逗號/範圍）")
    ps.add_argument("--out", default="../data", help="輸出根目錄（預設 ../data）")
    args = parser.parse_args(argv)

    if args.command == "current-term":
        client = CatalogClient()
        try:
            print(detect_current_term(client))
        finally:
            client.close()
        return 0

    if args.command == "migrate-pipeline-v2":
        from ntut_catalog.migrate_v2 import migrate
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
        summary = migrate(Path(args.data))
        print(json.dumps(summary.to_json(), ensure_ascii=False, indent=1))
        return 0

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "pipeline":
        _setup_logging(out_dir, f"pipeline-{args.cadence}")
        return _cmd_pipeline(args, out_dir)

    if args.command == "merge":
        return _cmd_merge(args, out_dir)

    if args.command == "derive":
        started = time.monotonic()
        manifest = derive(out_dir)
        n_files = sum(1 for p in (out_dir / "v1").rglob("*") if p.is_file())
        print(f"derive done: {len(manifest.terms)} terms, {len(manifest.calendars)} calendars, "
              f"{n_files} files in {time.monotonic() - started:.1f}s")
        return 0

    if args.command == "pua-scan":
        from ntut_catalog.pua_scan import format_report, scan_canonical
        hits = scan_canonical(out_dir, expand_terms(args.terms))
        if hits:
            print(format_report(hits), file=sys.stderr)
            return 1
        print("pua-scan clean")
        return 0

    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
