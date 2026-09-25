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
    details = crawl_detail(FakeDetailClient(), "115-1", offerings)
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
    crawl_detail(client, "115-1", offerings)
    assert client.curr_calls == 1   # 去重：兩個 offering 同編碼 → Curr 只抓一次


def test_write_details_writes_canonical_only(tmp_path):
    """spec §1／§4：crawl-detail 只寫 canonical——不寫 v1、不帶爬取時間、不存逐週進度。"""
    offerings = [_offering("360748", "2B04001", [{"snum": "360748", "teacher_code": "12567"}])]
    details = crawl_detail(FakeDetailClient(), "115-1", offerings)
    path = write_details(details, tmp_path)
    assert path == tmp_path / "canonical" / "115-1" / "details.ndjson"
    nd = path.read_text(encoding="utf-8").splitlines()
    assert len(nd) == 1
    CourseDetail.model_validate_json(nd[0])
    raw = json.loads(nd[0])
    assert "generated_at" not in raw
    assert all("weekly_progress" not in s for s in raw["syllabi"])
    assert not (tmp_path / "v1").exists()


def test_recrawl_of_unchanged_upstream_is_byte_identical(tmp_path):
    """上游沒變 → details.ndjson 逐位元組相同（R2 ETag 跳過、App 拿得到 304 的前提）。"""
    offerings = [_offering("360748", "2B04001", [{"snum": "360748", "teacher_code": "12567"}])]
    path = write_details(crawl_detail(FakeDetailClient(), "115-1", offerings), tmp_path)
    first = path.read_bytes()
    write_details(crawl_detail(FakeDetailClient(), "115-1", offerings), tmp_path)
    assert path.read_bytes() == first
