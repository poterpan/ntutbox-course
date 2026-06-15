"""離線重算既有 canonical 的學制欄位（不重爬）。

背景：早期 normalize 只把 matric 碼塞進 raw_fields["matric_codes"]（debug 區），
未升為第一級的 matric_codes / matric_division。修正所需輸入都已在本地——
raw_fields["matric_codes"] 是逗號分隔的碼字串，純解析即可回算，毋須再打 aps.ntut.edu.tw。

只動每課的 matric_codes / matric_division，其餘欄位 round-trip 不變（同一 model_dump_json）。
比照 reprocess.recategorize_canonical 的模式。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from models import CourseOffering, select_matric_division

logger = logging.getLogger(__name__)


def _codes_from_raw(course: CourseOffering) -> List[str]:
    """從 raw_fields["matric_codes"]（逗號分隔）取碼集合；無則回 []。"""
    raw = (course.raw_fields or {}).get("matric_codes", "")
    return sorted({c for c in (s.strip() for s in raw.split(",")) if c})


def rematric_canonical(out_dir: Path) -> List[dict]:
    """對每學期 canonical catalog.ndjson 依 raw_fields["matric_codes"] 回算學制欄位。

    回傳統計：每學期 {term, courses, rematriced}（rematriced = matric_codes/division 有變更的課數）。
    """
    canonical = out_dir / "canonical"
    stats: List[dict] = []
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
                codes = _codes_from_raw(c)
                division = select_matric_division(set(codes))
                if codes != c.matric_codes or division != c.matric_division:
                    changed += 1
                c.matric_codes = codes
                c.matric_division = division
                f.write(c.model_dump_json(exclude_none=False) + "\n")
        stats.append({"term": term_dir.name, "courses": len(courses), "rematriced": changed})
        logger.info("[%s] rematriced %d/%d", term_dir.name, changed, len(courses))
    return stats
