import json

from models import (
    ClassDirectory,
    CourseOffering,
    Enrollment,
    EnrollmentLatest,
    LocalizedText,
    Manifest,
    PeriodTable,
    Selection,
    TermCatalog,
    TermInfo,
)
from ntut_catalog.artifacts import (
    build_v1,
    structural_catalog,
    structural_course,
    write_canonical,
    write_enrollment_snapshot,
)


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


def test_write_canonical_structural(tmp_path, sample_result):
    write_canonical(sample_result, tmp_path)
    d = tmp_path / "canonical" / "115-1"
    nd = (d / "catalog.ndjson").read_text(encoding="utf-8").strip().splitlines()
    first = json.loads(nd[0])
    assert first["enrollment"]["enrolled_count"] is None   # 結構檔不含數字
    assert "enrolled" not in first["raw_fields"]
    assert (d / "classes.json").exists()
    ClassDirectory.model_validate_json((d / "classes.json").read_text(encoding="utf-8"))


def test_write_enrollment_snapshot(tmp_path, sample_result):
    write_enrollment_snapshot(
        sample_result.catalog.term.key, sample_result.enrollment, tmp_path, "2026-06-13"
    )
    snap = (tmp_path / "canonical" / "115-1" / "enrollment" / "2026-06-13.ndjson")
    lines = snap.read_text(encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[0])
    assert set(rec) == {"offering_id", "enrolled_count", "withdrawn_count", "observed_at"}
    assert len(lines) == len(sample_result.catalog.courses)


def test_build_v1_from_canonical(tmp_path, sample_result):
    write_canonical(sample_result, tmp_path)
    write_enrollment_snapshot(sample_result.catalog.term.key, sample_result.enrollment, tmp_path, "2026-06-13")
    build_v1(tmp_path, "2026-06-13T01:00:00+08:00")
    t = tmp_path / "v1" / "terms" / "115-1"
    cat = TermCatalog.model_validate_json((t / "catalog.json").read_text(encoding="utf-8"))
    assert cat.generated_at is None
    assert cat.courses[0].enrollment.enrolled_count is None      # v1 catalog 也純結構
    enr = EnrollmentLatest.model_validate_json((t / "enrollment.json").read_text(encoding="utf-8"))
    assert enr.counts                                            # 最新 snapshot 還原數字
    ClassDirectory.model_validate_json((t / "classes.json").read_text(encoding="utf-8"))
    PeriodTable.model_validate_json((t / "periods.json").read_text(encoding="utf-8"))
    man = Manifest.model_validate_json((tmp_path / "v1" / "manifest.json").read_text(encoding="utf-8"))
    assert "115-1" in man.terms


def test_build_v1_covers_all_terms(tmp_path, sample_result):
    write_canonical(sample_result, tmp_path)
    write_enrollment_snapshot(sample_result.catalog.term.key, sample_result.enrollment, tmp_path, "2026-06-13")
    # 第二學期 canonical
    r2 = sample_result
    r2.catalog.term.key = "114-2"
    r2.catalog.term.year = 114
    r2.catalog.term.semester = 2
    write_canonical(r2, tmp_path)
    write_enrollment_snapshot(r2.catalog.term.key, r2.enrollment, tmp_path, "2026-06-13")
    build_v1(tmp_path, "2026-06-13T01:00:00+08:00")
    man = Manifest.model_validate_json((tmp_path / "v1" / "manifest.json").read_text(encoding="utf-8"))
    assert {"115-1", "114-2"} <= set(man.terms)                  # manifest 涵蓋全部學期
