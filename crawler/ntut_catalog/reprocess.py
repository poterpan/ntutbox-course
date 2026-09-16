"""離線重處理既有 canonical（不重爬）：requirement.category、weekly_progress。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import json

from models import CourseDetail, CourseOffering, TermCalendarFile
from ntut_catalog.parse_progress import PARSER_VERSION, attach_weekly_progress, progress_report
from ntut_catalog.requirement_legend import build_requirement

logger = logging.getLogger(__name__)


def recategorize_canonical(out_dir: Path) -> List[dict]:
    """對每學期 canonical catalog.ndjson 依 requirement.symbol 重設 category/label_zh。"""
    canonical = out_dir / "canonical"
    stats = []
    for term_dir in sorted(p for p in canonical.iterdir() if p.is_dir()) if canonical.exists() else []:
        nd = term_dir / "catalog.ndjson"
        if not nd.exists():
            continue
        courses = [
            CourseOffering.model_validate_json(line)
            for line in nd.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        changed = 0
        with nd.open("w", encoding="utf-8") as f:
            for c in courses:
                new_req = build_requirement(c.requirement.symbol)
                if new_req.category != c.requirement.category or new_req.label_zh != c.requirement.label_zh:
                    changed += 1
                c.requirement = new_req
                f.write(c.model_dump_json(exclude_none=False) + "\n")
        stats.append({"term": term_dir.name, "courses": len(courses), "recategorized": changed})
        logger.info("[%s] recategorized %d/%d", term_dir.name, changed, len(courses))
    return stats


def load_term(out_dir: Path, term_key: str):
    """讀該學期 canonical/{term}/calendar.json 的 AcademicTerm（契約三）。沒有就回 None。

    逐週進度的日期／錨點規則需要它（weeks[] 用來映射、midterm/final_exam 當錨點）；
    沒有週次表時那些規則自動跳過，marker 路徑照常運作。
    """
    p = out_dir / "canonical" / term_key / "calendar.json"
    if not p.exists():
        return None
    cal = TermCalendarFile.model_validate_json(p.read_text(encoding="utf-8"))
    return cal.terms.get(term_key)


def reprocess_progress(out_dir: Path, term_keys: List[str], now: str) -> List[dict]:
    """對指定學期的 canonical details.ndjson 重算 weekly_progress 並寫回 + 產 report。

    `parser_version` 升版時不必重爬學校系統就能重產（照 recategorize/rematric 的先例）。
    """
    stats = []
    for term_key in term_keys:
        nd = out_dir / "canonical" / term_key / "details.ndjson"
        if not nd.exists():
            logger.warning("[%s] 沒有 details.ndjson，跳過", term_key)
            continue
        term = load_term(out_dir, term_key)
        details = [CourseDetail.model_validate_json(line)
                   for line in nd.read_text(encoding="utf-8").splitlines() if line.strip()]
        for d in details:
            attach_weekly_progress(d.syllabi, term, now)
        with nd.open("w", encoding="utf-8") as f:
            for d in sorted(details, key=lambda x: x.offering_id):
                f.write(d.model_dump_json() + "\n")
        report = progress_report(details, term_key, now, term is not None)
        rp = out_dir / "canonical" / "reports" / term_key
        rp.mkdir(parents=True, exist_ok=True)
        (rp / "weekly-progress.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        logger.info("[%s] weekly_progress 重產：%s", term_key, report["status_counts"])
        stats.append(report)
    return stats
