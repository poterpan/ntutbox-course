"""產物輸出：canonical NDJSON（git）+ v1 JSON artifacts（→ R2）+ manifest。

佈局（docs/DESIGN.md §4.5）：
  data/canonical/{term}/catalog.ndjson      一行一課（diff/審查/重建用）
  data/v1/terms/{term}/catalog.json         TermCatalog（web 主檔）
  data/v1/terms/{term}/classes.json         ClassDirectory
  data/v1/terms/{term}/periods.json         PeriodTable
  data/v1/terms/{term}/enrollment.json      EnrollmentLatest（volatile overlay）
  data/v1/manifest.json                     sha256/size/dataset_version
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from models import (
    CourseOffering,
    Enrollment,
    EnrollmentLatest,
    Freshness,
    Manifest,
    ManifestEntry,
    ManifestTerm,
    TermCatalog,
    TermInfo,
)
from ntut_catalog.orchestrator import TermResult
from ntut_catalog.periods import build_period_table

# normalize.py 寫入 raw_fields 的 volatile 鍵（人數/撤選），結構檔需剔除以免每日 churn
_VOLATILE_RAW_KEYS = ("enrolled", "withdrawn")


def structural_course(c: CourseOffering) -> CourseOffering:
    """回傳去掉 volatile enrollment（含 raw_fields 人數欄）的課程副本，**不 mutate 原物件**。"""
    s = c.model_copy(deep=True)
    s.enrollment = Enrollment()  # 全 None；capacity 本即 None
    s.raw_fields = {k: v for k, v in s.raw_fields.items() if k not in _VOLATILE_RAW_KEYS}
    return s


def structural_catalog(cat: TermCatalog) -> TermCatalog:
    """回傳純結構 catalog：去爬取時間戳 + 每課去 volatile，**不 mutate 原物件**。"""
    s = cat.model_copy(deep=True)
    s.generated_at = None
    s.freshness = Freshness()
    s.courses = [structural_course(c) for c in s.courses]
    return s


def write_canonical(result: TermResult, out_dir: Path) -> None:
    """寫 canonical（git 真相）：結構化 catalog.ndjson + classes.json。"""
    term = result.catalog.term.key
    d = out_dir / "canonical" / term
    d.mkdir(parents=True, exist_ok=True)
    with (d / "catalog.ndjson").open("w", encoding="utf-8") as f:
        for course in result.catalog.courses:
            f.write(structural_course(course).model_dump_json(exclude_none=False) + "\n")
    (d / "classes.json").write_text(result.classes.model_dump_json(), encoding="utf-8")


def write_enrollment_snapshot(result: TermResult, out_dir: Path, date: str) -> None:
    """寫 enrollment 時序快照（append-only，每日一檔）：offering_id + 人數/撤選 + observed_at。"""
    d = out_dir / "canonical" / result.catalog.term.key / "enrollment"
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{date}.ndjson").open("w", encoding="utf-8") as f:
        for oid, e in result.enrollment.counts.items():
            f.write(
                json.dumps(
                    {
                        "offering_id": oid,
                        "enrolled_count": e.enrolled_count,
                        "withdrawn_count": e.withdrawn_count,
                        "observed_at": e.observed_at,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def build_v1(out_dir: Path, generated_at: str) -> Manifest:
    """從【全部】canonical 學期重建完整 v1（catalog/classes/periods/enrollment）+ manifest。

    catalog 純結構（無時間戳）；enrollment.json 取該學期【最新】snapshot 還原數字。
    """
    canonical = out_dir / "canonical"
    periods_json = build_period_table().model_dump_json()
    for term_dir in sorted(p for p in canonical.iterdir() if p.is_dir()) if canonical.exists() else []:
        term = term_dir.name
        cat_nd = term_dir / "catalog.ndjson"
        if not cat_nd.exists():
            continue
        year, sem = int(term.split("-")[0]), int(term.split("-")[1])
        courses = [
            CourseOffering.model_validate_json(line)
            for line in cat_nd.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        catalog = TermCatalog(
            term=TermInfo(key=term, year=year, semester=sem, label=f"{year} 學年度第 {sem} 學期"),
            generated_at=None,
            courses=courses,
        )
        v1 = out_dir / "v1" / "terms" / term
        v1.mkdir(parents=True, exist_ok=True)
        (v1 / "catalog.json").write_text(catalog.model_dump_json(), encoding="utf-8")
        (v1 / "classes.json").write_text(
            (term_dir / "classes.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
        (v1 / "periods.json").write_text(periods_json, encoding="utf-8")
        # 最新 snapshot → enrollment.json overlay
        snaps = sorted((term_dir / "enrollment").glob("*.ndjson")) if (term_dir / "enrollment").exists() else []
        counts: dict = {}
        observed = None
        if snaps:
            for line in snaps[-1].read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                counts[r["offering_id"]] = Enrollment(
                    enrolled_count=r["enrolled_count"],
                    withdrawn_count=r["withdrawn_count"],
                    observed_at=r["observed_at"],
                )
                observed = r["observed_at"]
        (v1 / "enrollment.json").write_text(
            EnrollmentLatest(term_key=term, observed_at=observed, counts=counts).model_dump_json(),
            encoding="utf-8",
        )
    return write_manifest(out_dir, generated_at)


def _entry(path: Path, rel_url: str) -> ManifestEntry:
    data = path.read_bytes()
    return ManifestEntry(url=rel_url, sha256=hashlib.sha256(data).hexdigest(), size=len(data))


def write_manifest(out_dir: Path, generated_at: str) -> Manifest:
    terms_dir = out_dir / "v1" / "terms"
    terms = {}
    for term_dir in sorted(terms_dir.iterdir()) if terms_dir.exists() else []:
        if not term_dir.is_dir():
            continue
        term = term_dir.name
        files = {}
        for name in ["catalog", "classes", "periods", "enrollment"]:
            p = term_dir / f"{name}.json"
            if p.exists():
                files[name] = _entry(p, f"terms/{term}/{name}.json")
        if "catalog" not in files:
            continue
        # dataset_version = catalog.json 的結構 sha256（catalog 純結構→byte 穩定→版本穩定）
        terms[term] = ManifestTerm(
            catalog=files["catalog"],
            classes=files.get("classes"),
            periods=files.get("periods"),
            enrollment=files.get("enrollment"),
            dataset_version=files["catalog"].sha256,
        )
    manifest = Manifest(generated_at=generated_at, terms=terms)
    (out_dir / "v1" / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    return manifest
