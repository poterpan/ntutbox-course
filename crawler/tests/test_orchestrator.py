import json
from pathlib import Path

import pytest

from models import (
    ClassDirectory,
    ClassKind,
    EnrollmentLatest,
    Manifest,
    PeriodTable,
    TermCatalog,
)
from ntut_catalog.artifacts import build_v1, write_canonical, write_enrollment_snapshot
from ntut_catalog.orchestrator import crawl_term, parse_term_key
from tests._fakes import FakeClient

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_term_key():
    assert parse_term_key("114-1") == (114, 1)
    assert parse_term_key("110-2") == (110, 2)


@pytest.fixture(scope="module")
def result():
    return crawl_term(FakeClient(), "114-1", "2026-06-13T00:00:00+08:00")


def test_crawl_term_counts(result):
    assert len(result.catalog.courses) == 62
    assert result.catalog.term.key == "114-1"
    by_id = {c.offering_id: c for c in result.catalog.courses}
    c = by_id["347322"]
    assert c.unit_code == "59"
    assert c.division_group is not None and c.division_group.value == "day"
    assert c.raw_fields["matric_codes"] == "7"


def test_classes_merged(result):
    by_code = {c.code: c for c in result.classes.classes}
    assert by_code["3032"].unit_code == "59"          # 來自 Subj -3
    assert by_code["2798"].kind == ClassKind.regular  # 課程列也有
    assert len(result.classes.classes) >= 5


def test_embedded_classes_joined_from_directory(result):
    """回歸測試：課程內嵌班級須帶 directory 的 unit_code/grade（非舊版全 None）。"""
    by_id = {c.offering_id: c for c in result.catalog.courses}
    cl = by_id["347322"].classes[0]
    assert cl.code == "2798"
    assert cl.unit_code == "59"      # 從 Subj -3 join 回來（舊 bug 為 None）
    assert cl.grade == 4
    # directory 與內嵌副本對同一 code 的 kind 一致
    dir_by_code = {c.code: c for c in result.classes.classes}
    assert cl.kind == dir_by_code["2798"].kind


def test_enrollment_overlay(result):
    assert result.enrollment.counts["347322"].enrolled_count == 8
    assert result.enrollment.counts["347322"].capacity is None


def test_crawl_enrollment_light_path():
    """enrollment-only：只取人/撤，不需 catalog/classes。"""
    from ntut_catalog.orchestrator import crawl_enrollment

    enr = crawl_enrollment(FakeClient(), "114-1", "2026-06-13T14:00:00+08:00")
    assert enr.term_key == "114-1"
    assert enr.observed_at == "2026-06-13T14:00:00+08:00"
    assert len(enr.counts) == 62
    assert enr.counts["347322"].enrolled_count == 8
    assert enr.counts["347322"].withdrawn_count == 0
    assert enr.counts["347322"].capacity is None
    assert enr.counts["347315"].enrolled_count == 0


def test_artifacts_roundtrip(result, tmp_path):
    # 新管線：write_canonical + snapshot → build_v1 重建完整 v1
    write_canonical(result, tmp_path)
    write_enrollment_snapshot(result.catalog.term.key, result.enrollment, tmp_path, "2026-06-13")
    build_v1(tmp_path, "2026-06-13T00:00:00+08:00")
    term_dir = tmp_path / "v1" / "terms" / "114-1"

    # 所有檔案 round-trip 過 models 驗證
    TermCatalog.model_validate_json((term_dir / "catalog.json").read_text(encoding="utf-8"))
    ClassDirectory.model_validate_json((term_dir / "classes.json").read_text(encoding="utf-8"))
    PeriodTable.model_validate_json((term_dir / "periods.json").read_text(encoding="utf-8"))
    EnrollmentLatest.model_validate_json((term_dir / "enrollment.json").read_text(encoding="utf-8"))

    ndjson = (tmp_path / "canonical" / "114-1" / "catalog.ndjson").read_text(encoding="utf-8")
    assert len(ndjson.strip().splitlines()) == 62

    manifest = Manifest.model_validate_json(
        (tmp_path / "v1" / "manifest.json").read_text(encoding="utf-8")
    )
    entry = manifest.terms["114-1"].catalog
    import hashlib
    data = (term_dir / "catalog.json").read_bytes()
    assert entry.sha256 == hashlib.sha256(data).hexdigest()
    assert entry.size == len(data)
    # dataset_version = 結構 catalog 的 sha256（不再是爬取時間戳）
    assert manifest.terms["114-1"].dataset_version == entry.sha256
