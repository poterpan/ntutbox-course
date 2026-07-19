"""微學程 + 課程標準 爬取編排。"""
from __future__ import annotations

import logging

from models import (
    MicroProgram,
    MicroProgramCourse,
    MicroProgramDirectory,
    StandardDirectory,
)
from ntut_catalog.parse_course_table import parse_course_rows
from ntut_catalog.parse_program import (
    normalize_mprogram_category,
    parse_cprog_divisions,
    parse_cprog_matrics,
    parse_cprog_rules,
    parse_cprog_standard,
    parse_mprogram_list,
)

logger = logging.getLogger(__name__)


def _term(term_key: str):
    y, s = term_key.split("-")
    return int(y), int(s)


def crawl_mprograms(client, term_key: str) -> MicroProgramDirectory:
    year, sem = _term(term_key)
    programs = []
    entries = list(parse_mprogram_list(client.mprogram_list(year, sem)))
    # 上游若改版但仍回 HTTP 200，解析會得到 0 個學程。此時拋錯（fail loud），
    # 避免 programs=[] 被當成合法結果覆寫並清空既有 canonical 微學程資料。
    if not entries:
        raise ValueError(
            f"[{term_key}] SearchMProgram 解析出 0 個微學程——疑似上游改版，"
            f"中止以保留既有資料"
        )
    for code, name in entries:
        try:
            rows = parse_course_rows(client.mprogram(year, sem, code))
            oids = [r.offering_id for r in rows]
        except ValueError:
            oids = []  # 該學程本學期無開課
        # 併入課程標準（Cprog -4/matric=H）+ 相關規定原文。
        # 單一學程失敗只降級（courses=[]/rules_text=None），不中斷整個 crawl。
        # 抓取／規則／課程各自 try：一門壞課不得丟掉整段規則原文，反之亦然。
        courses: list[MicroProgramCourse] = []
        rules_text = None
        cprog_html = None
        try:
            cprog_html = client.cprog("-4", year=year, matric="H", division=code)
        except Exception:  # noqa: BLE001
            logger.warning("[%s] cprog -4 fetch failed for %s", term_key, code, exc_info=True)
        if cprog_html is not None:
            try:
                rules_text = parse_cprog_rules(cprog_html)
            except Exception:  # noqa: BLE001
                logger.warning("[%s] cprog -4 rules parse failed for %s", term_key, code, exc_info=True)
            try:
                std = parse_cprog_standard(cprog_html, entry_year=year, matric="H", division=code)
                parsed: list[MicroProgramCourse] = []
                for sc in std.courses:
                    if not sc.course_code:
                        continue
                    category, emi = normalize_mprogram_category(sc.notes)
                    parsed.append(MicroProgramCourse(
                        course_code=sc.course_code, name_zh=sc.name_zh, credits=sc.credits,
                        category=category, category_raw=(sc.notes or None), emi=emi))
                courses = parsed
            except Exception:  # noqa: BLE001
                logger.warning("[%s] cprog -4 courses parse failed for %s", term_key, code, exc_info=True)
            if rules_text is None:
                logger.warning("[%s] cprog -4 no rules_text for %s", term_key, code)
        programs.append(MicroProgram(code=code, name=name, offering_ids=oids,
                                     courses=courses, rules_text=rules_text))
    logger.info("[%s] mprograms: %d programs", term_key, len(programs))
    return MicroProgramDirectory(term_key=term_key, programs=programs)


def crawl_standards(client, entry_year: int) -> StandardDirectory:
    """Cprog -2(學制) → -3(系所) → -4(課程標準葉) 全展開某入學年。"""
    programs = []
    for matric, _mname in parse_cprog_matrics(client.cprog("-2", year=entry_year)):
        try:
            div_html = client.cprog("-3", year=entry_year, matric=matric)
        except Exception as e:  # noqa: BLE001
            logger.warning("cprog -3 %s/%s failed: %s", entry_year, matric, e)
            continue
        for division, _dname in parse_cprog_divisions(div_html):
            try:
                leaf = client.cprog("-4", year=entry_year, matric=matric, division=division)
            except Exception as e:  # noqa: BLE001
                logger.warning("cprog -4 %s/%s/%s failed: %s", entry_year, matric, division, e)
                continue
            std = parse_cprog_standard(leaf, entry_year, matric, division)
            if std.courses:
                programs.append(std)
    logger.info("entry_year %s standards: %d programs", entry_year, len(programs))
    return StandardDirectory(entry_year=entry_year, programs=programs)
