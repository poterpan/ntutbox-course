"""離線重建課程內嵌班級的 kind/unit_code/grade（不重爬學校系統）。

用途：normalize 早期版本建內嵌 ClassRef 時漏填 kind/unit_code/grade（全 regular/None）。
修正所需的全部輸入都已在本地：classes.json 是 kind/unit/grade 的單一真相、
catalog/NDJSON 已內嵌 class code → 純 join 即可修補，毋須再打 aps.ntut.edu.tw。

只動每課的 classes 欄位，其餘欄位 round-trip 不變（同一 model_dump_json）。

PUA 正規化的權威路徑是 publish 前的 build_v1；此離線工具讀的 v1 catalog 已正規化，
故 v1 寫回仍套 normalize_pua 只是防禦式一致（同 detail.py），輸入乾淨時為 no-op。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

from models import ClassDirectory, ClassRef, TermCatalog
from ntut_catalog.artifacts import write_manifest
from ntut_catalog.classes_builder import resolve_class_ref
from ntut_catalog.pua import normalize_pua

logger = logging.getLogger(__name__)


def rederive_term(term_dir: Path) -> dict:
    """重建單一學期的內嵌班級欄位。回傳統計（修補課數、fallback 數）。"""
    classes = ClassDirectory.model_validate_json(
        (term_dir / "classes.json").read_text(encoding="utf-8")
    )
    lookup: Dict[str, ClassRef] = {c.code: c for c in classes.classes}

    catalog = TermCatalog.model_validate_json(
        (term_dir / "catalog.json").read_text(encoding="utf-8")
    )
    patched = 0
    fallback = 0
    for course in catalog.courses:
        new_classes = []
        changed = False
        for cl in course.classes:
            ref = resolve_class_ref(cl.code, cl.name, lookup)
            if cl.code not in lookup:
                fallback += 1
            if ref != cl:
                changed = True
            new_classes.append(ref)
        course.classes = new_classes
        if changed:
            patched += 1

    (term_dir / "catalog.json").write_text(
        normalize_pua(catalog.model_dump_json()), encoding="utf-8"
    )

    canonical = term_dir.parents[2] / "canonical" / catalog.term.key / "catalog.ndjson"
    if canonical.exists():
        with canonical.open("w", encoding="utf-8") as f:
            for course in catalog.courses:
                f.write(course.model_dump_json(exclude_none=False) + "\n")

    return {"term": catalog.term.key, "courses": len(catalog.courses),
            "patched": patched, "fallback": fallback}


def rederive_all(out_dir: Path, generated_at: str) -> list[dict]:
    terms_dir = out_dir / "v1" / "terms"
    stats = []
    for term_dir in sorted(terms_dir.iterdir()):
        if term_dir.is_dir() and (term_dir / "catalog.json").exists():
            s = rederive_term(term_dir)
            stats.append(s)
            logger.info("[%s] rederived: %d courses, %d patched, %d fallback",
                        s["term"], s["courses"], s["patched"], s["fallback"])
    write_manifest(out_dir, generated_at)
    return stats
