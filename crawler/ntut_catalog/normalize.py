"""RawCourseRow → models.CourseOffering 正規化。

規則出處 docs/DESIGN.md：
  - 佔位課：notes 以「請選」開頭 或 credit==0 且無教師（§4.7）
  - capacity 來源不存在 → 恆 None；單雙週不存在 → week_pattern=weekly（§4.7）
  - 數字欄解析失敗 → None + 原文進 raw_fields（不猜）
  - selection.cwish_subj = offering_id；candidate_cunums = 開課班級碼（§4.6）
"""
from __future__ import annotations

from typing import Dict, Optional, Set

from models import (
    ClassRef,
    CourseOffering,
    DivisionGroup,
    Enrollment,
    EntityRef,
    LocalizedText,
    Meeting,
    Requirement,
    Selection,
    SourceRefs,
    WeekPattern,
)
from ntut_catalog.classes_builder import resolve_class_ref
from ntut_catalog.parse_course_table import RawCourseRow

# 單一學制碼 → 學制大類（QueryCurrPage 下拉實測 2026-06-13）：
# 5=日五專 6=日二技 7=日四技；8=碩 9=博 A=進修碩專班 C=週末碩 D=EMBA；
# 0=進修學院二技 4=進修部二技 F=進修部四技；1=學程 E=學士後學位學程
_MATRIC_DIVISION = {
    "5": DivisionGroup.day, "6": DivisionGroup.day, "7": DivisionGroup.day,
    "8": DivisionGroup.graduate, "9": DivisionGroup.graduate,
    "A": DivisionGroup.graduate, "C": DivisionGroup.graduate, "D": DivisionGroup.graduate,
    "0": DivisionGroup.extension, "4": DivisionGroup.extension, "F": DivisionGroup.extension,
    "1": DivisionGroup.program, "E": DivisionGroup.program,
}
_DIVISION_PRIORITY = [DivisionGroup.day, DivisionGroup.graduate,
                      DivisionGroup.extension, DivisionGroup.program]


def matric_codes_to_division(codes: Set[str]) -> Optional[DivisionGroup]:
    groups = {_MATRIC_DIVISION.get(c, DivisionGroup.other) for c in codes}
    if not groups:
        return None
    for g in _DIVISION_PRIORITY:
        if g in groups:
            return g
    return DivisionGroup.other


def _num(raw: Optional[str], raw_fields: dict, key: str) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        raw_fields[key] = raw
        return None


def _int(raw: Optional[str], raw_fields: dict, key: str) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        raw_fields[key] = raw
        return None


def to_offering(
    row: RawCourseRow,
    *,
    term_key: str,
    unit_code: Optional[str],
    unit_name: Optional[str],
    matric_codes: Set[str],
    observed_at: str,
    class_lookup: Optional[Dict[str, ClassRef]] = None,
) -> CourseOffering:
    raw_fields: dict = {}
    if row.raw_cells:
        raw_fields["cells"] = "\n".join(row.raw_cells)
    if matric_codes:
        raw_fields["matric_codes"] = ",".join(sorted(matric_codes))

    credits = _num(row.credits_raw, raw_fields, "credits")
    hours = _num(row.hours_raw, raw_fields, "hours")
    stage = _int(row.stage_raw, raw_fields, "stage")

    meetings = [
        Meeting(day=day, periods=tokens, week_pattern=WeekPattern.weekly)
        for day, tokens in sorted(row.day_periods.items())
        if tokens
    ]

    is_placeholder = row.notes.startswith("請選") or (credits == 0.0 and not row.teachers)

    lookup = class_lookup or {}
    classes = [resolve_class_ref(c, n, lookup) for c, n in row.classes]

    return CourseOffering(
        term_key=term_key,
        offering_id=row.offering_id,
        course_code=row.course_code,
        name=LocalizedText(zh=row.name_zh),
        credits=credits,
        hours=hours,
        stage=stage,
        stage_raw=row.stage_raw,
        requirement=Requirement(symbol=row.req_symbol),
        division_group=matric_codes_to_division(matric_codes),
        unit_code=unit_code,
        unit_name=unit_name,
        classes=classes,
        teachers=[EntityRef(code=c, name=n) for c, n in row.teachers],
        classrooms=[EntityRef(code=c, name=n) for c, n in row.classrooms],
        meetings=meetings,
        language=row.language,
        notes_raw=row.notes,
        is_placeholder=is_placeholder,
        interdisciplinary=row.interdisciplinary,
        enrollment=Enrollment(
            enrolled_count=_int(row.enrolled_raw, raw_fields, "enrolled"),
            capacity=None,  # 來源不提供（僅 cwish live 可知）
            withdrawn_count=_int(row.withdrawn_raw, raw_fields, "withdrawn"),
            observed_at=observed_at,
        ),
        selection=Selection(
            cwish_subj=row.offering_id,
            candidate_cunums=[c for c, _ in row.classes],
        ),
        source_refs=SourceRefs(
            curr_code=row.course_code,
            syllabus=[{"snum": s, "teacher_code": t} for s, t in row.syllabus],
        ),
        raw_fields=raw_fields,
    )
