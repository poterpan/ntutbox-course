"""逐學期爬取編排（策略見 docs/superpowers/plans/2026-06-13-crawler-p0.md）。

每學期：
  1. Subj.jsp -2 → 系所清單；每系所 Subj.jsp -3 → 班級清單
  2. 每系所 QueryCourse(matric=全校13碼, unit=系所) → 課程列 + unit 歸屬
  3. 13 × QueryCourse(matric=單一碼, unit=＊) → offering_id→學制碼 → division_group
     （同時當完整性 cross-check：只在 matric 查詢出現的課 → unit=None + 警告）
  4. 合併去重 → CourseOffering；頁尾節次表 vs 靜態表驗證
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from models import (
    ClassDirectory,
    CourseOffering,
    EnrollmentLatest,
    PeriodTable,
    TermCatalog,
    TermInfo,
)
from ntut_catalog.classes_builder import build_class_directory
from ntut_catalog.client import ALL_MATRIC_CODES, ALL_UNITS, SCHOOL_MATRIC, CatalogClient
from ntut_catalog.normalize import to_offering
from ntut_catalog.parse_course_table import RawCourseRow, parse_course_rows
from ntut_catalog.parse_subj import parse_classes, parse_departments
from ntut_catalog.periods import build_period_table, parse_footer_periods

logger = logging.getLogger(__name__)


@dataclass
class TermResult:
    catalog: TermCatalog
    classes: ClassDirectory
    enrollment: EnrollmentLatest
    periods: PeriodTable
    warnings: List[str] = field(default_factory=list)


def parse_term_key(term_key: str) -> Tuple[int, int]:
    year_s, sem_s = term_key.split("-")
    return int(year_s), int(sem_s)


def crawl_term(client: CatalogClient, term_key: str, now_iso: str) -> TermResult:
    year, sem = parse_term_key(term_key)
    warnings: List[str] = []

    # 1. 系所 + 班級
    depts = parse_departments(client.subj("-2", year, sem))
    if not depts:
        warnings.append(f"{term_key}: Subj -2 回空系所清單（學期未公布？）")
    subj_classes: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    for code, name in depts:
        try:
            subj_classes[(code, name)] = parse_classes(client.subj("-3", year, sem, code))
        except Exception as e:  # noqa: BLE001 — 單一系所失敗記警告續跑
            warnings.append(f"{term_key}: Subj -3 {code}({name}) 失敗: {e}")

    # 2. 每系所課程列（unit 歸屬）
    rows_by_id: Dict[str, RawCourseRow] = {}
    unit_of: Dict[str, Tuple[str, str]] = {}
    dup_across_units = 0
    for code, name in depts:
        try:
            rows = parse_course_rows(client.query_course(year, sem, SCHOOL_MATRIC, code))
        except ValueError:
            warnings.append(f"{term_key}: unit={code}({name}) 回應無課程表頭，當作 0 課")
            continue
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{term_key}: unit={code}({name}) 爬取失敗: {e}")
            continue
        for row in rows:
            if row.offering_id in rows_by_id:
                dup_across_units += 1
                continue
            rows_by_id[row.offering_id] = row
            unit_of[row.offering_id] = (code, name)
    if dup_across_units:
        warnings.append(f"{term_key}: {dup_across_units} 列課程出現在多個系所查詢（已去重，保留首見 unit）")

    # 3. 學制碼對映 + 完整性 cross-check
    matric_of: Dict[str, Set[str]] = {}
    footer_checked = False
    for mcode in ALL_MATRIC_CODES:
        try:
            html = client.query_course(year, sem, f"'{mcode}'", ALL_UNITS)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{term_key}: matric='{mcode}' 全系所查詢失敗: {e}（division 對映不完整）")
            continue
        if not footer_checked:
            footer = parse_footer_periods(html)
            static = {p.token: (p.start_hm, p.end_hm) for p in build_period_table().periods}
            if footer and footer != static:
                warnings.append(f"{term_key}: ⚠️ 頁尾節次表與靜態表不一致: {footer}")
            footer_checked = True
        try:
            rows = parse_course_rows(html)
        except ValueError:
            continue  # 該學制本學期無課
        for row in rows:
            matric_of.setdefault(row.offering_id, set()).add(mcode)
            if row.offering_id not in rows_by_id:
                rows_by_id[row.offering_id] = row
                unit_of[row.offering_id] = (None, None)  # type: ignore[assignment]
    orphan = [oid for oid, (u, _) in unit_of.items() if u is None]
    if orphan:
        warnings.append(f"{term_key}: {len(orphan)} 課只出現在學制查詢、未被任何系所收（unit=None）: {orphan[:10]}")
    no_matric = sum(1 for oid in rows_by_id if oid not in matric_of)
    if no_matric:
        warnings.append(f"{term_key}: {no_matric} 課未出現在任何單一學制查詢（division_group=None）")

    # 4. 先建班級目錄（單一真相），再以它的 lookup 填充每課內嵌班級的 kind/unit_code/grade
    course_classes = [(code, name) for row in rows_by_id.values() for code, name in row.classes]
    classes = build_class_directory(term_key, subj_classes, course_classes)
    class_lookup = {c.code: c for c in classes.classes}

    # 5. 正規化
    offerings: List[CourseOffering] = []
    for oid, row in sorted(rows_by_id.items()):
        unit_code, unit_name = unit_of.get(oid, (None, None))
        offerings.append(
            to_offering(
                row,
                term_key=term_key,
                unit_code=unit_code,
                unit_name=unit_name,
                matric_codes=matric_of.get(oid, set()),
                observed_at=now_iso,
                class_lookup=class_lookup,
            )
        )
    malformed = [c.offering_id for c in offerings if "cells" in c.raw_fields]
    if malformed:
        warnings.append(f"{term_key}: {len(malformed)} 列欄數異常進 raw_fields: {malformed[:10]}")
    if not offerings:
        warnings.append(f"{term_key}: ⚠️ 整學期 0 課（未公布或爬取失敗）")

    catalog = TermCatalog(
        term=TermInfo(key=term_key, year=year, semester=sem, label=f"{year} 學年度第 {sem} 學期"),
        generated_at=now_iso,
        freshness={"catalog_crawled_at": now_iso, "enrollment_observed_at": now_iso},
        courses=offerings,
    )
    return TermResult(
        catalog=catalog,
        classes=classes,
        enrollment=EnrollmentLatest(
            term_key=term_key,
            observed_at=now_iso,
            counts={c.offering_id: c.enrollment for c in offerings},
        ),
        periods=build_period_table(),
        warnings=warnings,
    )
