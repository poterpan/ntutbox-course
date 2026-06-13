from models import (
    CourseOffering,
    Enrollment,
    LocalizedText,
    Selection,
    TermCatalog,
    TermInfo,
)
from ntut_catalog.artifacts import structural_catalog, structural_course


def _course():
    return CourseOffering(
        term_key="115-1",
        offering_id="300001",
        name=LocalizedText(zh="x"),
        selection=Selection(cwish_subj="300001"),
        enrollment=Enrollment(
            enrolled_count=73, withdrawn_count=2, observed_at="2026-06-13T00:00:00+08:00"
        ),
        raw_fields={"enrolled": "73", "withdrawn": "2", "matric_codes": "7"},
    )


def test_structural_course_strips_volatile_without_mutating():
    c = _course()
    s = structural_course(c)
    assert s.enrollment.enrolled_count is None
    assert s.enrollment.withdrawn_count is None
    assert s.enrollment.observed_at is None
    assert "enrolled" not in s.raw_fields and "withdrawn" not in s.raw_fields
    assert s.raw_fields["matric_codes"] == "7"          # 結構性 raw 保留
    # 原物件不被改動（overlay 來源安全）
    assert c.enrollment.enrolled_count == 73
    assert c.raw_fields["enrolled"] == "73"


def test_structural_catalog_strips_timestamps():
    cat = TermCatalog(
        term=TermInfo(key="115-1", year=115, semester=1),
        generated_at="2026-06-13T00:00:00+08:00",
        freshness={"catalog_crawled_at": "x", "enrollment_observed_at": "y"},
        courses=[_course()],
    )
    s = structural_catalog(cat)
    assert s.generated_at is None
    assert s.freshness.catalog_crawled_at is None
    assert s.freshness.enrollment_observed_at is None
    assert s.courses[0].enrollment.enrolled_count is None
    # 原物件不變
    assert cat.generated_at == "2026-06-13T00:00:00+08:00"
    assert cat.courses[0].enrollment.enrolled_count == 73
