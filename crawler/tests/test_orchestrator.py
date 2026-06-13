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
from ntut_catalog.artifacts import write_manifest, write_term
from ntut_catalog.client import ALL_UNITS, SCHOOL_MATRIC
from ntut_catalog.orchestrator import crawl_term, parse_term_key

FIXTURES = Path(__file__).parent / "fixtures"

EMPTY_TABLE = """<HTML><body><TABLE border=1><TR>
<TH>課號</TH><TH>課程名稱</TH><TH>階段</TH><TH>學分</TH><TH>時數</TH><TH>修</TH>
<TH>班級</TH><TH>教師</TH><TH>日</TH><TH>一</TH><TH>二</TH><TH>三</TH><TH>四</TH>
<TH>五</TH><TH>六</TH><TH>教室</TH><TH>人</TH><TH>撤</TH><TH>授課語言</TH>
<TH>教學大綱與進度表</TH><TH>備註</TH><TH>隨班附讀</TH><TH>實驗實習</TH><TH>跨領域</TH>
</TR></TABLE></body></HTML>"""

SUBJ2_ONE_DEPT = '<html><body><a href="Subj.jsp?format=-3&year=114&sem=1&code=59">資工系</a></body></html>'


class FakeClient:
    """回放 fixtures：一個系所(59)、單一學制 '7' 有課，其餘空。"""

    def __init__(self):
        self.csie = (FIXTURES / "qc_114-1_csie_day.html").read_text(encoding="utf-8")
        self.subj3 = (FIXTURES / "subj_-3_114-1_59.html").read_text(encoding="utf-8")

    def subj(self, format, year, sem, code=None):
        if format == "-2":
            return SUBJ2_ONE_DEPT
        if format == "-3" and code == "59":
            return self.subj3
        return "<html><body></body></html>"

    def query_course(self, year, sem, matric, unit):
        if unit == "59" and matric == SCHOOL_MATRIC:
            return self.csie
        if unit == ALL_UNITS and matric == "'7'":
            return self.csie  # 假設全部都是四技課
        return EMPTY_TABLE


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


def test_artifacts_roundtrip(result, tmp_path):
    write_term(result, tmp_path)
    write_manifest(tmp_path, "2026-06-13T00:00:00+08:00")
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
    assert manifest.terms["114-1"].dataset_version == "2026-06-13T00:00:00+08:00"
