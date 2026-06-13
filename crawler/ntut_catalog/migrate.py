"""一次性離線遷移：既有（內嵌 enrollment）canonical → 新格式（structural + snapshot）。

不重爬學校。每個學期：
  1. 讀舊 catalog.ndjson（CourseOffering 內嵌 enrollment）
  2. 抽出 enrollment → seed snapshot `enrollment/{observed-date}.ndjson`
  3. structural_course 重寫 catalog.ndjson（去 volatile + raw_fields 人數欄）
  4. classes.json 若不在 canonical → 從 v1/terms/{term}/classes.json 複製過來
最後 build_v1 重建完整 v1。

冪等：catalog 已結構化（enrolled_count 全 None）→ 跳過該學期 seed/重寫，不以 null 覆寫既有 snapshot。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from models import CourseOffering
from ntut_catalog.artifacts import build_v1, structural_course

logger = logging.getLogger(__name__)


def _already_structural(courses: list[CourseOffering]) -> bool:
    return bool(courses) and all(c.enrollment.enrolled_count is None for c in courses)


def migrate_term(term_dir: Path, v1_terms_dir: Path, fallback_date: str) -> dict:
    term = term_dir.name
    cat_nd = term_dir / "catalog.ndjson"
    courses = [
        CourseOffering.model_validate_json(line)
        for line in cat_nd.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    # classes.json 落 canonical（若缺）
    canon_classes = term_dir / "classes.json"
    if not canon_classes.exists():
        src = v1_terms_dir / term / "classes.json"
        if src.exists():
            canon_classes.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    if _already_structural(courses):
        logger.info("[%s] already structural, skip seed/rewrite", term)
        return {"term": term, "migrated": False, "courses": len(courses)}

    # seed snapshot：日期取 observed_at 的前 10 字（同批爬取統一），缺則 fallback
    observed = next((c.enrollment.observed_at for c in courses if c.enrollment.observed_at), None)
    date = (observed or fallback_date)[:10]
    snap_dir = term_dir / "enrollment"
    snap_dir.mkdir(parents=True, exist_ok=True)
    with (snap_dir / f"{date}.ndjson").open("w", encoding="utf-8") as f:
        for c in courses:
            e = c.enrollment
            f.write(
                json.dumps(
                    {
                        "offering_id": c.offering_id,
                        "enrolled_count": e.enrolled_count,
                        "withdrawn_count": e.withdrawn_count,
                        "observed_at": e.observed_at,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    # 重寫 structural catalog.ndjson
    with cat_nd.open("w", encoding="utf-8") as f:
        for c in courses:
            f.write(structural_course(c).model_dump_json(exclude_none=False) + "\n")

    return {"term": term, "migrated": True, "courses": len(courses), "snapshot": f"{date}.ndjson"}


def migrate_all(out_dir: Path, generated_at: str) -> list[dict]:
    canonical = out_dir / "canonical"
    v1_terms = out_dir / "v1" / "terms"
    fallback = generated_at[:10]
    stats = []
    for term_dir in sorted(p for p in canonical.iterdir() if p.is_dir()):
        if (term_dir / "catalog.ndjson").exists():
            s = migrate_term(term_dir, v1_terms, fallback)
            stats.append(s)
            logger.info("[%s] migrated=%s courses=%d", s["term"], s["migrated"], s["courses"])
    build_v1(out_dir, generated_at)
    return stats
