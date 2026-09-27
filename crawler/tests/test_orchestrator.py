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
from tests._fakes import record_enrollment
from ntut_catalog.artifacts import build_v1, write_canonical
from ntut_catalog.orchestrator import crawl_term, parse_term_key
from tests._fakes import EMPTY_TABLE, FakeClient
from ntut_catalog.client import ALL_UNITS, SCHOOL_MATRIC

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
    """enrollment-only：只取人/撤，不需 catalog/classes。預設走全校一次查。"""
    from ntut_catalog.orchestrator import crawl_enrollment

    enr, source = crawl_enrollment(FakeClient(), "114-1", "2026-06-13T14:00:00+08:00")
    assert source == "school"
    assert enr.term_key == "114-1"
    assert enr.observed_at == "2026-06-13T14:00:00+08:00"
    assert len(enr.counts) == 62
    assert enr.counts["347322"].enrolled_count == 8
    assert enr.counts["347322"].withdrawn_count == 0
    assert enr.counts["347322"].capacity is None
    assert enr.counts["347315"].enrolled_count == 0


class _RecordingClient(FakeClient):
    """記下每次 query_course 的參數；`school` 決定全校查詢的行為（html／例外）。"""

    def __init__(self, school=None):
        super().__init__()
        self.calls = []
        self.school = school

    def query_course(self, year, sem, matric, unit, **kw):
        self.calls.append((matric, unit, kw))
        if unit == ALL_UNITS and matric == SCHOOL_MATRIC and self.school is not None:
            if isinstance(self.school, Exception):
                raise self.school
            return self.school
        return super().query_course(year, sem, matric, unit, **kw)


def test_crawl_enrollment_school_query_is_one_request_with_its_own_timeout():
    from ntut_catalog.orchestrator import (SCHOOL_QUERY_ATTEMPTS, SCHOOL_QUERY_TIMEOUT,
                                           crawl_enrollment)
    client = _RecordingClient()
    _, source = crawl_enrollment(client, "114-1", "t")
    assert source == "school"
    assert client.calls == [(SCHOOL_MATRIC, ALL_UNITS,
                             {"timeout": SCHOOL_QUERY_TIMEOUT, "attempts": SCHOOL_QUERY_ATTEMPTS})]
    assert (SCHOOL_QUERY_TIMEOUT, SCHOOL_QUERY_ATTEMPTS) == (180.0, 2)


@pytest.mark.parametrize("school", [
    RuntimeError("request failed after 2 attempts: QueryCourse.jsp"),   # 兩次都逾時
    "<html><body>no table</body></html>",                               # 無課程表頭
    EMPTY_TABLE,                                                        # 0 課
])
def test_crawl_enrollment_falls_back_to_per_dept(school):
    from ntut_catalog.orchestrator import crawl_enrollment
    client = _RecordingClient(school=school)
    enr, source = crawl_enrollment(client, "114-1", "t")
    assert source == "per-dept"
    assert len(enr.counts) == 62
    # 第一個請求是全校查詢，其後逐系所（這裡只有 59），不帶覆寫參數
    assert client.calls[0][:2] == (SCHOOL_MATRIC, ALL_UNITS)
    assert client.calls[1:] == [(SCHOOL_MATRIC, "59", {})]


def test_crawl_enrollment_school_and_per_dept_parse_identically():
    """同一份表格走兩條路徑，得到逐欄相同的人數表（2026-09-27 live 實測也是 0 差異）。"""
    from ntut_catalog.orchestrator import crawl_enrollment
    school, s1 = crawl_enrollment(_RecordingClient(), "114-1", "t")
    per_dept, s2 = crawl_enrollment(_RecordingClient(school=RuntimeError("x")), "114-1", "t")
    assert (s1, s2) == ("school", "per-dept")
    assert school.model_dump() == per_dept.model_dump()


def test_client_request_override_limits_attempts_and_sets_timeout(monkeypatch):
    """單次覆寫：attempts=2 只打 2 次、timeout 傳給 httpx；不影響 client 預設。"""
    import httpx
    from ntut_catalog import client as client_mod
    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)
    seen = []

    def handler(request):
        seen.append(request.extensions.get("timeout"))
        raise httpx.ReadTimeout("slow", request=request)

    c = client_mod.CatalogClient(max_retries=4)
    c._client = httpx.Client(base_url=client_mod.BASE_URL,
                             transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="after 2 attempts"):
        c.query_course(115, 1, SCHOOL_MATRIC, ALL_UNITS, timeout=180.0, attempts=2)
    assert len(seen) == 2
    assert seen[0]["read"] == 180.0
    seen.clear()
    with pytest.raises(RuntimeError, match="after 5 attempts"):
        c.query_course(115, 1, SCHOOL_MATRIC, "59")      # 預設：max_retries+1 次
    assert len(seen) == 5


def test_artifacts_roundtrip(result, tmp_path):
    # 新管線：write_canonical + snapshot → build_v1 重建完整 v1
    write_canonical(result, tmp_path)
    record_enrollment(tmp_path, result.catalog.term.key, result.enrollment, "2026-06-13T00:00:00+08:00")
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
