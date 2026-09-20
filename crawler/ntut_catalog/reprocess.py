"""離線重處理既有 canonical（不重爬）。

三件事：依符號補 requirement.category；重算 weekly_progress；把 details 的
pass-through 欄位遷到 schema v3。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

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
            attach_weekly_progress(d.syllabi, term, now, course_name=d.name.zh)
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


# ---------------------------------------------------------- details 形狀遷移（schema v2 → v3）

# 這兩個是「上游決定欄位」的 pass-through 袋子，v3 起從 dict 換成有序的 label/value 陣列。
_PASS_THROUGH_FIELDS = ("flex_learning", "extra")


def migrate_detail_line(line: str) -> Tuple[str, int]:
    """一行 details.ndjson → (新行, 被改過的 syllabus 數)。已是新形狀則原樣回傳。

    **刻意不走 Pydantic round-trip。** `Syllabus` 沒有 `extra="forbid"`，未知欄位在
    `model_validate` 時被忽略、`model_dump` 時被丟掉；而 data branch 上的 115-1 已經帶了
    尚未併進 main 的 `weekly_progress`——round-trip 會靜默刪掉那個欄位。只動這兩個 key。

    dict → 陣列是無損的：`json.loads` 保留物件的出現順序（CPython dict 保序），
    所以轉出來的順序就是原始表格列序。
    """
    doc = json.loads(line)
    changed = 0
    for syl in doc.get("syllabi") or []:
        touched = False
        for field in _PASS_THROUGH_FIELDS:
            v = syl.get(field)
            if isinstance(v, dict):
                syl[field] = [{"label": k, "value": val} for k, val in v.items()]
                touched = True
        changed += touched
    if not changed:
        return line, 0
    # 與 models 的 model_dump_json() 同一種序列化（緊湊分隔、不跳脫非 ASCII），
    # 這樣遷移過的行與之後重爬寫出來的行格式一致，diff 不會整片變動。
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":")), changed


def migrate_details_canonical(out_dir: Path, terms: Optional[List[str]] = None) -> List[dict]:
    """把 canonical/{term}/details.ndjson 的 pass-through 欄位遷成 v3 形狀（不重爬）。

    為什麼需要：`crawl-detail` 只由週更 cron 跑**當前學期**（~5k 請求/學期），
    歷史學期要重爬得走 backfill（10 學期 ≈ 28,977 請求、~6.8 小時打學校的生產系統）。
    形狀轉換是純機械的，沒有理由為此重爬。**冪等**，重跑安全。
    """
    canonical = out_dir / "canonical"
    wanted = set(terms) if terms else None
    stats = []
    for term_dir in sorted(p for p in canonical.iterdir() if p.is_dir()) if canonical.exists() else []:
        if wanted is not None and term_dir.name not in wanted:
            continue
        nd = term_dir / "details.ndjson"
        if not nd.exists():
            continue
        out_lines, migrated = [], 0
        for line in nd.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            new_line, changed = migrate_detail_line(line)
            out_lines.append(new_line)
            migrated += changed
        if migrated:
            nd.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        stats.append({"term": term_dir.name, "courses": len(out_lines), "syllabi_migrated": migrated})
        logger.info("[%s] details migrated: %d syllabi in %d courses",
                    term_dir.name, migrated, len(out_lines))
    return stats
