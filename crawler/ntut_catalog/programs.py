"""微學程 + 課程標準 爬取編排。"""
from __future__ import annotations

import logging

from models import MicroProgram, MicroProgramDirectory, StandardDirectory
from ntut_catalog.parse_course_table import parse_course_rows
from ntut_catalog.parse_program import (
    parse_cprog_divisions,
    parse_cprog_matrics,
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
    for code, name in parse_mprogram_list(client.mprogram_list(year, sem)):
        try:
            rows = parse_course_rows(client.mprogram(year, sem, code))
            oids = [r.offering_id for r in rows]
        except ValueError:
            oids = []  # 該學程本學期無開課
        programs.append(MicroProgram(code=code, name=name, offering_ids=oids))
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
