"""課程詳情爬取：Curr.jsp（描述）+ ShowSyllabus.jsp（大綱）→ CourseDetail。

描述依 course_code 去重（跨學期/同課多班共用）；大綱逐 (snum, teacher_code) 抓。
輸出：canonical/{term}/details.ndjson（一課一行，git 可 diff）——**只寫 canonical**。
v1 的 course/{offering_id}.json 與逐週進度（weekly_progress）一律由 derive 產生
（spec §1、§4）：canonical 只存學校來的原文，不帶爬取時間、不存衍生欄位，
上游沒變時重爬出來的 details.ndjson 逐位元組相同。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from models import CourseDetail, CourseOffering, LocalizedText
from ntut_catalog.nodes import NodeTally
from ntut_catalog.parse_detail import parse_curr, parse_syllabus

logger = logging.getLogger(__name__)


def crawl_detail(
    client,
    term_key: str,
    offerings: List[CourseOffering],
    curr_cache: Optional[Dict[str, dict]] = None,
    tally: Optional[NodeTally] = None,
) -> List[CourseDetail]:
    """`tally`：一個課號＝一個節點。該課的 Curr 或任一份大綱抓取失敗 → 記
    `{"offering_id"}`（merge 會從 HEAD 沿用那一行，見 merge.py）。"""
    curr_cache = {} if curr_cache is None else curr_cache
    tally = tally if tally is not None else NodeTally()
    curr_failed: set = set()   # Curr 失敗也快取成 {}（請求量不變），同編碼的其他課號一樣算失敗
    details: List[CourseDetail] = []
    for off in offerings:
        tally.attempt()
        failed = False
        code = off.course_code
        curr: dict = {}
        if code:
            if code not in curr_cache:
                try:
                    curr_cache[code] = parse_curr(client.curr(code))
                except Exception as e:  # noqa: BLE001 — 單課失敗記警告續跑
                    logger.warning("[%s] Curr %s failed: %s", off.offering_id, code, e)
                    curr_cache[code] = {}
                    curr_failed.add(code)
            curr = curr_cache[code]
            failed = code in curr_failed

        syllabi = []
        for ref in (off.source_refs.syllabus if off.source_refs else []):
            snum, tc = ref.get("snum"), ref.get("teacher_code")
            if not snum:
                continue
            try:
                syllabi.append(parse_syllabus(client.syllabus(snum, tc), tc))
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] syllabus (%s,%s) failed: %s", off.offering_id, snum, tc, e)
                failed = True
        if failed:
            tally.fail(offering_id=off.offering_id)

        details.append(
            CourseDetail(
                term_key=term_key,
                offering_id=off.offering_id,
                course_code=code,
                name=LocalizedText(zh=off.name.zh, en=curr.get("name_en")),
                # Curr 失敗時 curr={}：zh 給空字串（LocalizedText.zh 不收 None，否則整輪崩潰）；
                # 這一行會被 merge 換成 HEAD 的版本或整行略過，不會以殘缺狀態進 canonical
                description=LocalizedText(
                    zh=curr.get("description_zh") or "", en=curr.get("description_en")
                ),
                syllabi=syllabi,
            )
        )
    return details


# canonical 不存衍生欄位：weekly_progress 由 derive 以現行 parser＋行事曆即時計算（spec §4）
_CANONICAL_EXCLUDE = {"syllabi": {"__all__": {"weekly_progress"}}}


def detail_line(detail: CourseDetail) -> str:
    """details.ndjson 的一行（canonical 形狀：不含 weekly_progress）。"""
    return detail.model_dump_json(exclude=_CANONICAL_EXCLUDE)


def write_details(details: List[CourseDetail], out_dir: Path) -> Optional[Path]:
    """寫 canonical/{term}/details.ndjson（依課號排序）。回傳寫出的路徑；空清單不寫、回 None。"""
    if not details:
        return None
    term = details[0].term_key
    canon = out_dir / "canonical" / term
    canon.mkdir(parents=True, exist_ok=True)
    path = canon / "details.ndjson"
    with path.open("w", encoding="utf-8") as f:
        for d in sorted(details, key=lambda x: x.offering_id):
            f.write(detail_line(d) + "\n")
    return path
