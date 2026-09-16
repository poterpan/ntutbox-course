"""課程詳情爬取：Curr.jsp（描述）+ ShowSyllabus.jsp（大綱）→ CourseDetail。

描述依 course_code 去重（跨學期/同課多班共用）；大綱逐 (snum, teacher_code) 抓。
輸出：canonical/{term}/details.ndjson（一課一行，git 可 diff）
     + v1/terms/{term}/course/{offering_id}.json（炸開，web 隨點隨取）
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from models import AcademicTerm, CourseDetail, CourseOffering, LocalizedText
from ntut_catalog.parse_detail import parse_curr, parse_syllabus
from ntut_catalog.parse_progress import attach_weekly_progress
from ntut_catalog.pua import normalize_pua

logger = logging.getLogger(__name__)


def crawl_detail(
    client,
    term_key: str,
    offerings: List[CourseOffering],
    now_iso: str,
    curr_cache: Optional[Dict[str, dict]] = None,
    term: Optional[AcademicTerm] = None,
) -> List[CourseDetail]:
    """term（契約三的該學期行事曆）只給逐週進度的日期／錨點規則用；沒有就跳過那些規則。"""
    curr_cache = {} if curr_cache is None else curr_cache
    details: List[CourseDetail] = []
    for off in offerings:
        code = off.course_code
        curr: dict = {}
        if code:
            if code not in curr_cache:
                try:
                    curr_cache[code] = parse_curr(client.curr(code))
                except Exception as e:  # noqa: BLE001 — 單課失敗記警告續跑
                    logger.warning("[%s] Curr %s failed: %s", off.offering_id, code, e)
                    curr_cache[code] = {}
            curr = curr_cache[code]

        syllabi = []
        for ref in (off.source_refs.syllabus if off.source_refs else []):
            snum, tc = ref.get("snum"), ref.get("teacher_code")
            if not snum:
                continue
            try:
                syllabi.append(parse_syllabus(client.syllabus(snum, tc), tc))
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] syllabus (%s,%s) failed: %s", off.offering_id, snum, tc, e)

        # 契約一：逐週進度是 schedule 的結構化衍生欄位，原文一律保留、不覆寫。
        attach_weekly_progress(syllabi, term, now_iso)

        details.append(
            CourseDetail(
                term_key=term_key,
                offering_id=off.offering_id,
                course_code=code,
                name=LocalizedText(zh=off.name.zh, en=curr.get("name_en")),
                description=LocalizedText(
                    zh=curr.get("description_zh"), en=curr.get("description_en")
                ),
                syllabi=syllabi,
                generated_at=now_iso,
            )
        )
    return details


def write_details(details: List[CourseDetail], out_dir: Path) -> None:
    if not details:
        return
    term = details[0].term_key
    canon = out_dir / "canonical" / term
    canon.mkdir(parents=True, exist_ok=True)
    with (canon / "details.ndjson").open("w", encoding="utf-8") as f:
        for d in sorted(details, key=lambda x: x.offering_id):
            f.write(d.model_dump_json() + "\n")
    course_dir = out_dir / "v1" / "terms" / term / "course"
    course_dir.mkdir(parents=True, exist_ok=True)
    for d in details:
        # canonical 保留原文（上面 details.ndjson）；v1 消費層做 PUA 正規化，與 build_v1 一致
        (course_dir / f"{d.offering_id}.json").write_text(
            normalize_pua(d.model_dump_json()), encoding="utf-8"
        )
