"""CLI：
  python -m ntut_catalog crawl    --terms 110-1:115-1 --out ../data   # 爬取
  python -m ntut_catalog rederive --out ../data                        # 離線重建內嵌班級（不重爬）

term 範圍只展開 sem 1/2（暑期 3 不在 P0 範圍）。
已存在的學期預設跳過（resume），--force 重抓。
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

from ntut_catalog.artifacts import build_v1, write_canonical, write_enrollment_snapshot
from ntut_catalog.client import CatalogClient, detect_current_term
from ntut_catalog.migrate import migrate_all
from ntut_catalog.orchestrator import crawl_enrollment, crawl_term, parse_term_key
from ntut_catalog.rederive import rederive_all

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


def _cmd_rederive(out_dir: Path) -> int:
    _setup_logging(out_dir, "rederive")
    stats = rederive_all(out_dir, datetime.now(TAIPEI).isoformat(timespec="seconds"))
    total_patched = sum(s["patched"] for s in stats)
    total_fallback = sum(s["fallback"] for s in stats)
    logger.info("rederive done: %d terms, %d courses patched, %d fallback (應為 0)",
                len(stats), total_patched, total_fallback)
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ntut_catalog")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("crawl", help="爬取課程目錄")
    p.add_argument("--terms", required=True, help="如 110-1:115-1 或 114-1,114-2")
    p.add_argument("--out", default="../data", help="輸出根目錄（預設 ../data）")
    p.add_argument("--delay", type=float, default=0.5, help="每請求基礎延遲秒數")
    p.add_argument("--force", action="store_true", help="已存在的學期也重抓")
    r = sub.add_parser("rederive", help="離線重建課程內嵌班級欄位（不重爬）")
    r.add_argument("--out", default="../data", help="輸出根目錄（預設 ../data）")
    sub.add_parser("current-term", help="偵測學校當前學期並印出（如 115-1）")
    m = sub.add_parser("migrate", help="既有資料離線遷移成 structural canonical + snapshot（不重爬）")
    m.add_argument("--out", default="../data", help="輸出根目錄（預設 ../data）")
    re = sub.add_parser("refresh-enrollment",
                        help="選課季輕量人數刷新：只抓人/撤、寫 hourly snapshot、重建 v1")
    re.add_argument("--terms", required=True, help="當前學期，如 115-1（可逗號多個）")
    re.add_argument("--out", default="../data", help="輸出根目錄（預設 ../data）")
    re.add_argument("--delay", type=float, default=0.5, help="每請求基礎延遲秒數")
    args = parser.parse_args(argv)

    if args.command == "current-term":
        client = CatalogClient()
        try:
            print(detect_current_term(client))
        finally:
            client.close()
        return 0

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "rederive":
        return _cmd_rederive(out_dir)

    if args.command == "migrate":
        _setup_logging(out_dir, "migrate")
        stats = migrate_all(out_dir, datetime.now(TAIPEI).isoformat(timespec="seconds"))
        logger.info("migrate done: %d terms (%d migrated)",
                    len(stats), sum(1 for s in stats if s["migrated"]))
        return 0

    if args.command == "refresh-enrollment":
        _setup_logging(out_dir, "refresh-enrollment")
        terms = expand_terms(args.terms)
        now_iso = datetime.now(TAIPEI).isoformat(timespec="seconds")
        hour_stamp = datetime.now(TAIPEI).strftime("%Y-%m-%dT%H")  # hourly 顆粒
        client = CatalogClient(delay_range=(args.delay * 0.8, args.delay * 1.6))
        failed: List[str] = []
        try:
            for term in terms:
                if not term_already_done(out_dir, term):
                    logger.warning("[%s] no canonical catalog — 先 crawl 再 refresh；跳過", term)
                    continue
                logger.info("[%s] refreshing enrollment ...", term)
                try:
                    enr = crawl_enrollment(client, term, now_iso)
                except Exception:
                    logger.exception("[%s] enrollment refresh failed", term)
                    failed.append(term)
                    continue
                write_enrollment_snapshot(term, enr, out_dir, hour_stamp)
                logger.info("[%s] enrollment: %d courses @ %s (requests: %d)",
                            term, len(enr.counts), hour_stamp, client.request_count)
        finally:
            client.close()
        build_v1(out_dir, now_iso)
        logger.info("enrollment refresh done. failed: %s", failed or "none")
        return 1 if failed else 0

    _setup_logging(out_dir, "crawl")
    terms = expand_terms(args.terms)
    logger.info("terms to crawl: %s", terms)
    today = datetime.now(TAIPEI).strftime("%Y-%m-%d")
    client = CatalogClient(delay_range=(args.delay * 0.8, args.delay * 1.6))
    failed: List[str] = []
    crawled_any = False
    try:
        for term in terms:
            if term_already_done(out_dir, term) and not args.force:
                logger.info("[%s] canonical exists, skip (use --force to recrawl)", term)
                continue
            now_iso = datetime.now(TAIPEI).isoformat(timespec="seconds")
            logger.info("[%s] crawling ...", term)
            try:
                result = crawl_term(client, term, now_iso)
            except Exception:
                logger.exception("[%s] crawl failed", term)
                failed.append(term)
                continue
            write_canonical(result, out_dir)
            write_enrollment_snapshot(result.catalog.term.key, result.enrollment, out_dir, today)
            crawled_any = True
            logger.info(
                "[%s] done: %d courses, %d classes, %d warnings (requests so far: %d)",
                term, len(result.catalog.courses), len(result.classes.classes),
                len(result.warnings), client.request_count,
            )
            for w in result.warnings:
                logger.warning("[%s] %s", term, w)
    finally:
        client.close()

    # 從【全部】canonical 重建完整 v1（manifest 涵蓋所有學期，不只本次爬的）
    build_v1(out_dir, datetime.now(TAIPEI).isoformat(timespec="seconds"))
    logger.info(
        "v1 rebuilt + manifest written. crawled=%s, total requests: %d, failed terms: %s",
        crawled_any, client.request_count, failed or "none",
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
