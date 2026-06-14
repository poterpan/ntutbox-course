import json
from pathlib import Path

from models import (
    CourseDetail,
    CourseOffering,
    LocalizedText,
    Selection,
    SourceRefs,
)
from ntut_catalog.detail import crawl_detail, write_details

FIXTURES = Path(__file__).parent / "fixtures"


class FakeDetailClient:
    def __init__(self):
        self.curr_html = (FIXTURES / "curr_2B04001.html").read_text(encoding="utf-8")
        self.syl_html = (FIXTURES / "syllabus_360748.html").read_text(encoding="utf-8")
        self.curr_calls = 0

    def curr(self, code):
        self.curr_calls += 1
        return self.curr_html

    def syllabus(self, snum, teacher_code):
        return self.syl_html


def _offering(oid, code, syl):
    return CourseOffering(
        term_key="115-1", offering_id=oid, course_code=code,
        name=LocalizedText(zh="英語簡報技巧(一)"),
        selection=Selection(cwish_subj=oid),
        source_refs=SourceRefs(curr_code=code, syllabus=syl),
    )


def test_crawl_detail_builds_detail():
    offerings = [_offering("360748", "2B04001", [{"snum": "360748", "teacher_code": "12567"}])]
    details = crawl_detail(FakeDetailClient(), "115-1", offerings, "2026-06-14T00:00:00+08:00")
    assert len(details) == 1
    d = details[0]
    assert d.offering_id == "360748"
    assert d.name.zh == "英語簡報技巧(一)"
    assert d.name.en == "English Presentation Skills (I)"
    assert d.description.zh.startswith("本課程以語言教學目標")
    assert len(d.syllabi) == 1
    assert d.syllabi[0].teacher_name == "高銘宏"
    assert "W1." in d.syllabi[0].schedule


def test_crawl_detail_dedupes_curr_by_course_code():
    """同 course_code 的多個 offering 共用一次 Curr 抓取。"""
    client = FakeDetailClient()
    offerings = [
        _offering("360748", "2B04001", [{"snum": "360748", "teacher_code": "12567"}]),
        _offering("360749", "2B04001", [{"snum": "360749", "teacher_code": "12567"}]),
    ]
    crawl_detail(client, "115-1", offerings, "2026-06-14T00:00:00+08:00")
    assert client.curr_calls == 1   # 去重：兩個 offering 同編碼 → Curr 只抓一次


def test_write_details(tmp_path):
    offerings = [_offering("360748", "2B04001", [{"snum": "360748", "teacher_code": "12567"}])]
    details = crawl_detail(FakeDetailClient(), "115-1", offerings, "2026-06-14T00:00:00+08:00")
    write_details(details, tmp_path)
    # canonical ndjson
    nd = (tmp_path / "canonical" / "115-1" / "details.ndjson").read_text(encoding="utf-8").splitlines()
    assert len(nd) == 1
    CourseDetail.model_validate_json(nd[0])
    # v1 per-course file（隨點隨取）
    pc = tmp_path / "v1" / "terms" / "115-1" / "course" / "360748.json"
    assert pc.exists()
    CourseDetail.model_validate_json(pc.read_text(encoding="utf-8"))
