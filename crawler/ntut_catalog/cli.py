"""CLI：
  python -m ntut_catalog crawl    --terms 110-1:115-1 --out ../data   # 爬取
  python -m ntut_catalog rederive --out ../data                        # 離線重建內嵌班級（不重爬）
  python -m ntut_catalog rematric --out ../data                        # 離線回算學制欄位（不重爬）

term 範圍只展開 sem 1/2（暑期 3 不在 P0 範圍）。
已存在的學期預設跳過（resume），--force 重抓。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

from models import CourseOffering
from ntut_catalog.artifacts import build_v1, write_canonical, write_enrollment_snapshot
from ntut_catalog.client import CatalogClient, detect_current_term
from ntut_catalog.artifacts import (
    read_calendar_event_count,
    write_calendar_events,
    write_mprograms,
    write_standards,
    write_term_calendar,
)
from ntut_catalog.calendar_client import ICS_URL, CalendarClient
from ntut_catalog.calendar_events import crawl_calendar_events
from ntut_catalog.term_calendar import build_all_term_calendars, default_terms
from ntut_catalog.detail import crawl_detail, write_details
from ntut_catalog.programs import crawl_mprograms, crawl_standards
from ntut_catalog.migrate import migrate_all
from ntut_catalog.orchestrator import crawl_enrollment, crawl_term, parse_term_key
from ntut_catalog.rederive import rederive_all
from ntut_catalog.parse_progress import progress_report
from ntut_catalog.reprocess import load_term, reprocess_progress

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
    cd = sub.add_parser("crawl-detail",
                        help="爬課程描述(Curr)+教學大綱(ShowSyllabus) → details.ndjson + course/{id}.json")
    cd.add_argument("--terms", required=True, help="學期，如 115-1（可逗號多個）")
    cd.add_argument("--out", default="../data", help="輸出根目錄（預設 ../data）")
    cd.add_argument("--delay", type=float, default=0.5, help="每請求基礎延遲秒數")
    mp = sub.add_parser("crawl-mprograms", help="爬微學程(SearchMProgram) → mprograms.json")
    mp.add_argument("--terms", required=True, help="學期，如 115-1（可逗號多個）")
    mp.add_argument("--out", default="../data")
    mp.add_argument("--delay", type=float, default=0.5)
    st = sub.add_parser("crawl-standards", help="爬課程標準/畢業標準(Cprog) → standards/{year}.json")
    st.add_argument("--years", required=True, help="入學年，如 115（可逗號/範圍 110:115）")
    st.add_argument("--out", default="../data")
    st.add_argument("--delay", type=float, default=0.5)
    cal = sub.add_parser(
        "crawl-calendar",
        help="抓校網 Google Calendar ics → canonical/calendar + v1/calendar/events.json")
    cal.add_argument("--out", default="../data")
    cal.add_argument("--url", default=ICS_URL, help="覆寫來源 URL（測試用）")
    cal.add_argument("--terms", default=None,
                     help="要產週次表的學期（預設當前學年度兩個學期）")
    rp = sub.add_parser("reprocess-progress",
                        help="離線重算逐週進度 weekly_progress（不重爬）；parser 升版後用")
    rp.add_argument("--terms", required=True, help="學期，如 115-1（可逗號/範圍）")
    rp.add_argument("--out", default="../data")
    rc = sub.add_parser("recategorize", help="離線依符號補 requirement.category（不重爬）")
    rc.add_argument("--out", default="../data")
    rm = sub.add_parser("rematric", help="離線依 raw_fields.matric_codes 回算 matric_codes/matric_division（不重爬）")
    rm.add_argument("--out", default="../data")
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

    if args.command == "recategorize":
        from ntut_catalog.reprocess import recategorize_canonical
        _setup_logging(out_dir, "recategorize")
        stats = recategorize_canonical(out_dir)
        build_v1(out_dir, datetime.now(TAIPEI).isoformat(timespec="seconds"))
        logger.info("recategorize done: %d terms, %d courses recategorized",
                    len(stats), sum(s["recategorized"] for s in stats))
        return 0

    if args.command == "rematric":
        from ntut_catalog.rematric import rematric_canonical
        _setup_logging(out_dir, "rematric")
        stats = rematric_canonical(out_dir)
        build_v1(out_dir, datetime.now(TAIPEI).isoformat(timespec="seconds"))
        logger.info("rematric done: %d terms, %d courses rematriced",
                    len(stats), sum(s["rematriced"] for s in stats))
        return 0

    if args.command == "pua-scan":
        from ntut_catalog.pua_scan import format_report, scan_canonical
        hits = scan_canonical(out_dir, expand_terms(args.terms))
        if hits:
            print(format_report(hits), file=sys.stderr)
            return 1
        print("pua-scan clean")
        return 0

    if args.command == "crawl-mprograms":
        _setup_logging(out_dir, "crawl-mprograms")
        client = CatalogClient(delay_range=(args.delay * 0.8, args.delay * 1.6))
        try:
            for term in expand_terms(args.terms):
                write_mprograms(crawl_mprograms(client, term), out_dir)
        finally:
            client.close()
        build_v1(out_dir, datetime.now(TAIPEI).isoformat(timespec="seconds"))
        logger.info("crawl-mprograms done. requests: %d", client.request_count)
        return 0

    if args.command == "reprocess-progress":
        _setup_logging(out_dir, "reprocess-progress")
        now = datetime.now(TAIPEI).isoformat(timespec="seconds")
        reports = reprocess_progress(out_dir, expand_terms(args.terms), now)
        build_v1(out_dir, now)
        for r in reports:
            logger.info("[%s] %s，有 topic 的週次比例 %.4f",
                        r["term_key"], r["status_counts"], r["week_cells"]["rate"])
        return 0

    if args.command == "crawl-calendar":
        _setup_logging(out_dir, "crawl-calendar")
        client = CalendarClient()
        try:
            feed = crawl_calendar_events(
                client, args.url, previous_count=read_calendar_event_count(out_dir))
        finally:
            client.close()
        changed = write_calendar_events(feed, out_dir)
        # 週次表（契約三）從同一份事件推導——同源、同一次抓取，不另開一條管線。
        term_keys = expand_terms(args.terms) if args.terms else default_terms()
        calendars = build_all_term_calendars(
            feed.events, term_keys, feed.source.url, feed.source.content_sha256)
        for term_key, cal in calendars.items():
            write_term_calendar(cal, term_key, out_dir)
        logger.info("term calendars: %s", ", ".join(sorted(calendars)))
        build_v1(out_dir, datetime.now(TAIPEI).isoformat(timespec="seconds"))
        logger.info("crawl-calendar done. events: %d, canonical changed: %s, horizon %s (max %s)",
                    len(feed.events), changed,
                    "ok" if feed.horizon.ok else "INSUFFICIENT", feed.horizon.max_start)
        if not feed.horizon.ok:
            # 告警但**不阻斷發布**——feed 沒有新學年不代表現有資料壞了。
            # workflow 另有一步讀 canonical/calendar/meta.json 開/更新 issue（見 crawl.yml）。
            print(f"::warning title=行事曆 horizon 不足::feed 最遠只到 "
                  f"{feed.horizon.max_start}，新學年度資料尚未匯入")
        return 0

    if args.command == "crawl-standards":
        _setup_logging(out_dir, "crawl-standards")
        years = []
        for part in args.years.split(","):
            if ":" in part:
                a, b = part.split(":"); years += list(range(int(a), int(b) + 1))
            else:
                years.append(int(part))
        client = CatalogClient(delay_range=(args.delay * 0.8, args.delay * 1.6))
        try:
            for y in years:
                write_standards(crawl_standards(client, y), out_dir)
        finally:
            client.close()
        build_v1(out_dir, datetime.now(TAIPEI).isoformat(timespec="seconds"))
        logger.info("crawl-standards done. years: %s, requests: %d", years, client.request_count)
        return 0

    if args.command == "crawl-detail":
        _setup_logging(out_dir, "crawl-detail")
        terms = expand_terms(args.terms)
        now_iso = datetime.now(TAIPEI).isoformat(timespec="seconds")
        client = CatalogClient(delay_range=(args.delay * 0.8, args.delay * 1.6))
        failed: List[str] = []
        try:
            for term in terms:
                cat_nd = out_dir / "canonical" / term / "catalog.ndjson"
                if not cat_nd.exists():
                    logger.warning("[%s] no canonical catalog — 先 crawl 再 crawl-detail；跳過", term)
                    continue
                offerings = [
                    CourseOffering.model_validate_json(line)
                    for line in cat_nd.read_text(encoding="utf-8").splitlines() if line.strip()
                ]
                logger.info("[%s] crawl-detail: %d offerings ...", term, len(offerings))
                # 逐週進度的規則 (b)(c) 要吃契約三的 weeks[]；沒有就只跑 marker 路徑。
                term_obj = load_term(out_dir, term)
                if term_obj is None:
                    logger.warning("[%s] 沒有 calendar.json，逐週進度的日期類規則停用", term)
                try:
                    details = crawl_detail(client, term, offerings, now_iso,
                                           term=term_obj)
                except Exception:
                    logger.exception("[%s] crawl-detail failed", term)
                    failed.append(term)
                    continue
                write_details(details, out_dir)
                report = progress_report(details, term, now_iso, term_obj is not None)
                rp_dir = out_dir / "canonical" / "reports" / term
                rp_dir.mkdir(parents=True, exist_ok=True)
                (rp_dir / "weekly-progress.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                logger.info("[%s] weekly_progress: %s，有 topic 的週次比例 %.4f",
                            term, report["status_counts"], report["week_cells"]["rate"])
                with_desc = sum(1 for d in details if d.description.zh or d.description.en)
                with_syl = sum(1 for d in details if d.syllabi)
                logger.info("[%s] detail done: %d courses, %d 有描述, %d 有大綱 (requests: %d)",
                            term, len(details), with_desc, with_syl, client.request_count)
        finally:
            client.close()
        logger.info("crawl-detail done. total requests: %d, failed: %s",
                    client.request_count, failed or "none")
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
