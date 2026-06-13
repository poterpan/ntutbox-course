from pathlib import Path

import pytest

from models import ClassKind, ClassRef, DivisionGroup, WeekPattern
from ntut_catalog.parse_course_table import parse_course_rows
from ntut_catalog.normalize import matric_codes_to_division, to_offering

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def rows():
    html = (FIXTURES / "qc_114-1_csie_day.html").read_text(encoding="utf-8")
    return {r.offering_id: r for r in parse_course_rows(html)}


def _make(rows, oid, **kw):
    defaults = dict(term_key="114-1", unit_code="59", unit_name="資工系",
                    matric_codes=set(), observed_at="2026-06-13T00:00:00+08:00")
    defaults.update(kw)
    return to_offering(rows[oid], **defaults)


def test_full_offering_347322(rows):
    c = _make(rows, "347322", matric_codes={"7"})
    assert c.term_key == "114-1"
    assert c.offering_id == "347322"
    assert c.course_code == "5904319"
    assert c.name.zh == "嵌入式系統"
    assert c.credits == 3.0
    assert c.hours == 3.0
    assert c.stage == 1
    assert c.requirement.symbol == "★"
    assert [cl.code for cl in c.classes] == ["2798"]
    assert c.teachers[0].code == "12384" and c.teachers[0].name == "張世豪"
    assert len(c.meetings) == 1
    m = c.meetings[0]
    assert m.day == 5 and m.periods == ["5", "6", "7"]
    assert m.week_pattern == WeekPattern.weekly
    assert c.language == "英語"
    assert c.enrollment.enrolled_count == 8
    assert c.enrollment.withdrawn_count == 0
    assert c.enrollment.capacity is None          # 來源沒有，恆 None
    assert c.enrollment.observed_at == "2026-06-13T00:00:00+08:00"
    assert c.selection.cwish_subj == "347322"
    assert c.selection.candidate_cunums == ["2798"]
    assert c.division_group == DivisionGroup.day
    assert c.is_placeholder is False
    assert c.unit_code == "59"
    assert c.raw_fields["matric_codes"] == "7"


def test_embedded_class_filled_from_directory_lookup(rows):
    """內嵌班級的 kind/unit_code/grade 須來自 directory（單一真相），非預設 regular/None。"""
    lookup = {
        "2798": ClassRef(code="2798", name="資工四", kind=ClassKind.pool,
                         unit_code="59", grade=4),
    }
    c = _make(rows, "347322", class_lookup=lookup)
    assert len(c.classes) == 1
    cl = c.classes[0]
    assert cl.code == "2798"
    assert cl.kind == ClassKind.pool          # 直接採用 directory 的 kind（即使這裡是人為 pool）
    assert cl.unit_code == "59"
    assert cl.grade == 4


def test_embedded_class_fallback_classifies_by_name(rows):
    """code 不在 lookup（防呆）→ 依名稱現場分類，grade 仍可從名稱推得。"""
    c = _make(rows, "347322", class_lookup={})
    cl = c.classes[0]
    assert cl.code == "2798"
    assert cl.kind == ClassKind.regular       # 資工四 → regular
    assert cl.grade == 4                       # 名稱推導年級
    assert cl.unit_code is None                # fallback 不知歸屬


def test_meetings_sorted_by_day(rows):
    c = _make(rows, "347327")
    assert [(m.day, m.periods) for m in c.meetings] == [(2, ["5", "6"]), (3, ["6"])]


def test_no_teacher_zero_credit_is_not_auto_placeholder(rows):
    """347315 體育 1.0 學分無教師：非佔位（佔位=請選開頭 or credit0+無師）。"""
    c = _make(rows, "347315")
    assert c.is_placeholder is False
    assert c.teachers == []
    assert c.meetings == []


def test_placeholder_rules(rows):
    row = rows["347315"]
    row2 = type(row)(**{**row.__dict__})
    row2.notes = "請選博雅課程"
    assert to_offering(row2, term_key="114-1", unit_code=None, unit_name=None,
                       matric_codes=set(), observed_at="x").is_placeholder is True
    row3 = type(row)(**{**row.__dict__})
    row3.credits_raw = "0.0"
    assert to_offering(row3, term_key="114-1", unit_code=None, unit_name=None,
                       matric_codes=set(), observed_at="x").is_placeholder is True


def test_bad_numbers_go_to_raw_fields(rows):
    row = rows["347322"]
    row2 = type(row)(**{**row.__dict__})
    row2.credits_raw = "abc"
    c = to_offering(row2, term_key="114-1", unit_code=None, unit_name=None,
                    matric_codes=set(), observed_at="x")
    assert c.credits is None
    assert c.raw_fields["credits"] == "abc"


def test_matric_division_mapping():
    assert matric_codes_to_division({"7"}) == DivisionGroup.day
    assert matric_codes_to_division({"8", "9"}) == DivisionGroup.graduate
    assert matric_codes_to_division({"4"}) == DivisionGroup.extension
    assert matric_codes_to_division({"1"}) == DivisionGroup.program
    assert matric_codes_to_division(set()) is None
    # 混合時取多數決優先序 day > graduate > extension > program
    assert matric_codes_to_division({"7", "8"}) == DivisionGroup.day
