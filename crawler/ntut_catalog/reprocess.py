"""離線重處理既有 canonical（不重爬）。目前：依符號補 requirement.category。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from models import CourseOffering
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
