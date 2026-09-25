"""節點失敗的處理（spec §3「節點失敗的處理」）：fetcher 回報重試後仍失敗的節點，
merge 依資料集丟棄（catalog、失敗太多）或逐節點從 HEAD 沿用（standards／mprograms／details）。"""
import datetime as dt
import json
import shutil

import pytest

from models import (MicroProgram, MicroProgramCourse, MicroProgramDirectory, ProgramStandard,
                    StandardCourse, StandardDirectory)
from ntut_catalog import fetch_state as fs
from ntut_catalog import pipeline
from ntut_catalog.detail import crawl_detail
from ntut_catalog.ics import TAIPEI
from ntut_catalog.merge import merge_fetch_output
from ntut_catalog.nodes import NodeTally
from ntut_catalog.orchestrator import crawl_term
from ntut_catalog.programs import crawl_mprograms, crawl_standards
from tests._fakes import FakeClient
from tests.test_detail import FakeDetailClient, _offering
from tests.test_merge import _catalog_lines, _entry, _rows_text, _stage
from tests.test_pipeline import Clock, DailyFakeClient, _ctx
from tests.test_programs import FakeProgClient

T = "115-1"
CHECKED = "2026-09-28T03:00:00+08:00"


# ============================================================ fetcher 回報失敗節點

class _Boom(RuntimeError):
    pass


def test_catalog_reports_failed_dept_unit_and_matric():
    class Flaky(FakeClient):
        def subj(self, format, year, sem, code=None):
            if format == "-3":
                raise _Boom("Subj -3 500")
            return super().subj(format, year, sem, code)

        def query_course(self, year, sem, matric, unit):
            if unit == "59" or matric == "'A'":
                raise _Boom("QueryCourse 500")
            return super().query_course(year, sem, matric, unit)

    r = crawl_term(Flaky(), "114-1", "2026-06-13T00:00:00+08:00")
    assert r.failed_nodes == [{"dept": "59"}, {"unit": "59"}, {"matric": "A"}]
    assert r.node_total == 15          # 1 系所 ×（Subj -3＋QueryCourse）＋13 學制


def test_catalog_empty_unit_is_not_a_failure():
    """系所回應無課程表頭（該系本學期 0 課）是正常結果，不算節點失敗。"""
    r = crawl_term(FakeClient(), "114-1", "2026-06-13T00:00:00+08:00")
    assert r.failed_nodes == [] and r.node_total == 15


def _links(fmt, year, param, codes, **fixed):
    extra = "".join(f"&{k}={v}" for k, v in fixed.items())
    return "<html><body>" + "".join(
        f'<a href="./Cprog.jsp?format={fmt}&year={year}{extra}&{param}={c}">{c}</a>' for c in codes
    ) + "</body></html>"


class StdClient(FakeProgClient):
    """兩個學制（7、5）× 兩個系所（59、14F）的小課程標準樹；可指定哪些請求失敗。"""

    def __init__(self, fail=()):
        super().__init__()
        self.fail = set(fail)

    def cprog(self, format, **p):
        key = (format, p.get("matric"), p.get("division"))
        if key in self.fail:
            raise _Boom(f"cprog {key} 500")
        if format == "-2":
            return _links("-3", p["year"], "matric", ["7", "5"])
        if format == "-3":
            return _links("-4", p["year"], "division", ["59", "14F"], matric=p["matric"])
        return self.cleaf


def test_standards_reports_failed_matric_and_division():
    tally = NodeTally()
    d = crawl_standards(StdClient(fail={("-3", "5", None), ("-4", "7", "59")}), 115, tally=tally)
    assert [(p.matric, p.division) for p in d.programs] == [("7", "14F")]
    assert tally.failed == [{"year": 115, "matric": "7", "division": "59"},
                            {"year": 115, "matric": "5"}]
    assert tally.total == 4            # -3 ×2＋（學制 7 的）-4 ×2；學制 5 的 -4 從未嘗試


def test_mprograms_reports_failed_program_only_on_fetch_error():
    tally = NodeTally()
    d = crawl_mprograms(FakeProgClient(raising="AV9"), T, tally=tally)
    assert tally.failed == [{"program": "AV9"}] and tally.total == len(d.programs)
    broken = NodeTally()                # 錯誤頁（查無資料）＝請求成功、內容為空，不是節點失敗
    crawl_mprograms(FakeProgClient(broken="AV9"), T, tally=broken)
    assert broken.failed == []


def test_details_reports_offering_on_curr_or_syllabus_failure():
    class Flaky(FakeDetailClient):
        def curr(self, code):
            self.curr_calls += 1
            if code == "BAD":
                raise _Boom("Curr 500")
            return self.curr_html

        def syllabus(self, snum, teacher_code):
            if snum == "900003":
                raise _Boom("syllabus 500")
            return self.syl_html

    offerings = [_offering("900001", "BAD", [{"snum": "900001", "teacher_code": "1"}]),
                 _offering("900002", "BAD", [{"snum": "900002", "teacher_code": "1"}]),
                 _offering("900003", "2B04001", [{"snum": "900003", "teacher_code": "1"}]),
                 _offering("900004", "2B04001", [{"snum": "900004", "teacher_code": "1"}])]
    client, tally = Flaky(), NodeTally()
    crawl_detail(client, T, offerings, tally=tally)
    # 同編碼的第二個課號沿用失敗的 Curr 快取（請求量不變），也算失敗
    assert tally.failed == [{"offering_id": "900001"}, {"offering_id": "900002"},
                            {"offering_id": "900003"}]
    assert tally.total == 4 and client.curr_calls == 2


def test_pipeline_entry_carries_failed_nodes(tmp_path):
    class Flaky(DailyFakeClient):
        def query_course(self, year, sem, matric, unit):
            if matric == "'A'":
                raise _Boom("QueryCourse 500")
            return super().query_course(year, sem, matric, unit)

    clock = Clock(dt.datetime(2026, 9, 26, 6, 0, tzinfo=TAIPEI))
    result = pipeline.run("daily", ["catalog"], [T], tmp_path, tmp_path / "stage",
                          ctx=_ctx(tmp_path, clock, Flaky))
    (e,) = result.datasets
    assert e["ok"] and e["failed_nodes"] == [{"matric": "A"}] and e["node_total"] == 15
    written = json.loads((tmp_path / "stage" / "pipeline-result.json").read_text(encoding="utf-8"))
    assert written["datasets"][0]["failed_nodes"] == [{"matric": "A"}]


# ============================================================ merge：資料建構

def _std(year, keys, title="t"):
    return StandardDirectory(entry_year=year, programs=[
        ProgramStandard(entry_year=year, matric=m, division=d, title=f"{title}-{m}-{d}",
                        courses=[StandardCourse(course_code=f"C{m}{d}", name_zh="課", credits=3.0)])
        for m, d in keys]).model_dump_json()


HEAD_STD_KEYS = [("7", "59"), ("7", "14F"), ("5", "59"), ("5", "14F")]


def _mp(programs):
    return MicroProgramDirectory(term_key=T, programs=programs).model_dump_json()


def _prog(code, oids=("1",), courses=True, rules="規定"):
    return MicroProgram(code=code, name=f"學程{code}", offering_ids=list(oids),
                        courses=[MicroProgramCourse(course_code=f"K{code}", name_zh="課", credits=2.0,
                                                    category="核心")] if courses else [],
                        rules_text=rules)


def _detail(oid, desc="描述"):
    return json.dumps({"term_key": T, "offering_id": oid, "description": {"zh": desc}},
                      ensure_ascii=False)


def _details(lines):
    return "".join(x + "\n" for x in lines)


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.delenv("PARTIAL_FAILURE_MAX_RATIO", raising=False)
    monkeypatch.delenv("QUALITY_MIN_RATIO", raising=False)
    d = tmp_path / "data"
    c = d / "canonical"
    (c / "standards").mkdir(parents=True)
    (c / "standards" / "115.json").write_text(_std(115, HEAD_STD_KEYS), encoding="utf-8")
    (c / T).mkdir()
    (c / T / "mprograms.json").write_text(_mp([_prog("A"), _prog("B")]), encoding="utf-8")
    (c / T / "details.ndjson").write_text(_details([_detail(f"90000{i}") for i in range(1, 4)]),
                                          encoding="utf-8")
    (c / T / "catalog.ndjson").write_text(_catalog_lines(100, "head"), encoding="utf-8")
    (c / T / "classes.json").write_text("{}", encoding="utf-8")
    return d


def _head(data, rel):
    return (data / "canonical" / rel).read_bytes()


def _merge(tmp_path, data, name, term, rel, text, failed, node_total, **extra):
    stage = _stage(tmp_path, f"stage-{name}", [_entry(
        name, term, checked_at=CHECKED, files=[rel], failed_nodes=failed, node_total=node_total,
        **extra)], {rel: text}, cadence="weekly")
    return merge_fetch_output(stage, data)


# ============================================================ merge：standards

def test_standards_failed_division_carried_forward_byte_identical(tmp_path, data):
    before = _head(data, "standards/115.json")
    node = {"year": 115, "matric": "7", "division": "14F"}
    new = _std(115, [k for k in HEAD_STD_KEYS if k != ("7", "14F")])
    r = _merge(tmp_path, data, "standards", None, "standards/115.json", new, [node], 30)
    assert _head(data, "standards/115.json") == before            # 其他都沒變 → 逐位元組相同
    assert r.partial == [{"name": "standards", "term": None, "failed": 1, "node_total": 30,
                          "carried_forward": [node], "missing": []}]
    assert r.applied[0]["partial"] is True and r.applied[0]["failed_nodes"] == 1
    (a,) = r.alerts
    assert a["level"] == "warning" and "year=115/matric=7/division=14F" in a["message"]
    assert fs.get(fs.load(fs.path_for(data / "canonical")), "standards", None)["checked_at"] == CHECKED


def test_standards_failed_matric_carries_all_its_divisions(tmp_path, data):
    """-3 失敗（整個學制 7 沒展開）→ 沿用 HEAD 學制 7 的全部系所；其他系所的新內容照收。"""
    node = {"year": 115, "matric": "7"}
    new = _std(115, [("5", "59"), ("5", "14F")], title="new")
    _merge(tmp_path, data, "standards", None, "standards/115.json", new, [node], 30)
    got = StandardDirectory.model_validate_json(_head(data, "standards/115.json"))
    assert [(p.matric, p.division, p.title.split("-")[0]) for p in got.programs] == [
        ("7", "59", "t"), ("7", "14F", "t"), ("5", "59", "new"), ("5", "14F", "new")]


def test_standards_missing_in_head_is_reported(tmp_path, data):
    node = {"year": 115, "matric": "9", "division": "99"}
    new = _std(115, HEAD_STD_KEYS, title="new")
    r = _merge(tmp_path, data, "standards", None, "standards/115.json", new, [node], 30)
    assert _head(data, "standards/115.json") == new.encode("utf-8")
    assert r.partial[0]["carried_forward"] == [] and r.partial[0]["missing"] == [node]
    assert "缺漏 1 個：year=115/matric=9/division=99" in r.alerts[0]["message"]


def test_standards_new_year_without_head_file(tmp_path, data):
    node = {"year": 116, "matric": "7", "division": "59"}
    new = _std(116, [("7", "14F")])
    r = _merge(tmp_path, data, "standards", None, "standards/116.json", new, [node], 30)
    assert _head(data, "standards/116.json") == new.encode("utf-8")
    assert r.partial[0]["missing"] == [node]


# ============================================================ merge：mprograms

def test_mprograms_failed_program_carried_forward_byte_identical(tmp_path, data):
    rel = f"{T}/mprograms.json"
    before = _head(data, rel)
    new = _mp([_prog("A"), _prog("B", courses=False, rules=None)])     # Cprog -4 失敗的降級版
    r = _merge(tmp_path, data, "mprograms", T, rel, new, [{"program": "B"}], 40)
    assert _head(data, rel) == before
    assert r.partial[0]["carried_forward"] == [{"program": "B"}]


def test_mprograms_keeps_fresh_offering_ids(tmp_path, data):
    """失敗的只有 Cprog -4：courses／rules_text 沿用 HEAD，offering_ids 用本次成功抓到的。"""
    rel = f"{T}/mprograms.json"
    new = _mp([_prog("A"), _prog("B", oids=("7", "8"), courses=False, rules=None)])
    _merge(tmp_path, data, "mprograms", T, rel, new, [{"program": "B"}], 40)
    b = MicroProgramDirectory.model_validate_json(_head(data, rel)).programs[1]
    assert b.offering_ids == ["7", "8"] and b.rules_text == "規定" and len(b.courses) == 1


def test_mprograms_missing_in_head_keeps_degraded_entry(tmp_path, data):
    rel = f"{T}/mprograms.json"
    new = _mp([_prog("A"), _prog("B"), _prog("C", courses=False, rules=None)])
    r = _merge(tmp_path, data, "mprograms", T, rel, new, [{"program": "C"}], 40)
    assert _head(data, rel) == new.encode("utf-8")
    assert r.partial[0]["missing"] == [{"program": "C"}]


# ============================================================ merge：details

def test_details_failed_offering_carried_forward_byte_identical(tmp_path, data):
    rel = f"{T}/details.ndjson"
    before = _head(data, rel)
    new = _details([_detail("900001"), _detail("900002", desc=None), _detail("900003")])
    r = _merge(tmp_path, data, "details", T, rel, new, [{"offering_id": "900002"}], 60)
    assert _head(data, rel) == before
    assert r.partial[0]["carried_forward"] == [{"offering_id": "900002"}]


def test_details_missing_in_head_line_is_left_out(tmp_path, data):
    rel = f"{T}/details.ndjson"
    new = _details([_detail("900001", "新"), _detail("900002"), _detail("900003"),
                    _detail("900004", desc=None)])
    r = _merge(tmp_path, data, "details", T, rel, new, [{"offering_id": "900004"}], 60)
    assert _head(data, rel).decode("utf-8") == _details(
        [_detail("900001", "新"), _detail("900002"), _detail("900003")])
    assert r.partial[0]["missing"] == [{"offering_id": "900004"}]
    assert "缺漏 1 個：offering_id=900004" in r.alerts[0]["message"]


# ============================================================ merge：丟棄

def test_too_many_failures_drop_the_whole_dataset_term(tmp_path, data):
    rel = f"{T}/details.ndjson"
    before = _head(data, rel)
    failed = [{"offering_id": "900001"}, {"offering_id": "900002"}]
    r = _merge(tmp_path, data, "details", T, rel, _details([_detail("x")]), failed, 30)  # 6.7%
    assert _head(data, rel) == before
    assert [(d["name"], d["term"]) for d in r.dropped] == [("details", T)]
    assert r.applied == [] and r.partial == [] and r.alerts[0]["level"] == "error"
    assert "2/30" in r.alerts[0]["message"] and "offering_id=900001" in r.alerts[0]["message"]
    assert fs.get(fs.load(fs.path_for(data / "canonical")), "details", T) is None


def test_ratio_is_env_overridable(tmp_path, data, monkeypatch):
    monkeypatch.setenv("PARTIAL_FAILURE_MAX_RATIO", "0.5")
    rel = f"{T}/details.ndjson"
    failed = [{"offering_id": "900001"}, {"offering_id": "900002"}]
    r = _merge(tmp_path, data, "details", T, rel, _details([_detail("900001", None),
                                                            _detail("900002", None)]), failed, 4)
    assert not r.dropped and len(r.partial[0]["carried_forward"]) == 2


def test_failures_without_node_total_are_dropped(tmp_path, data):
    rel = f"{T}/details.ndjson"
    r = _merge(tmp_path, data, "details", T, rel, _details([_detail("x")]),
               [{"offering_id": "900001"}], None)
    assert r.dropped and r.applied == []


def test_catalog_any_failed_node_drops_term_including_enrollment(tmp_path, data):
    snap = "2026-09-26T0630"
    files = {f"{T}/catalog.ndjson": _catalog_lines(99, "partial"), f"{T}/classes.json": "{}",
             f"{T}/enrollment/{snap}.ndjson": _rows_text([{"offering_id": "300000"}])}
    stage = _stage(tmp_path, "stage", [_entry(
        "catalog", T, files=list(files), failed_nodes=[{"unit": "59"}], node_total=200,
        enrollment={"observed_at": "2026-09-26T06:30:00+08:00", "snapshot": snap})], files)
    r = merge_fetch_output(stage, data)
    canon = data / "canonical" / T
    assert (canon / "catalog.ndjson").read_text(encoding="utf-8") == _catalog_lines(100, "head")
    assert not (canon / "enrollment").exists()                     # 人數快照也不收、不追加觀測
    assert [(d["name"], d["term"]) for d in r.dropped] == [("catalog", T)]
    assert "unit=59" in r.alerts[0]["message"] and r.alerts[0]["level"] == "error"
    st = fs.load(fs.path_for(data / "canonical"))
    assert fs.get(st, "catalog", T) is None and fs.get(st, "enrollment", T) is None


# ============================================================ 端到端：pipeline → merge

def test_daily_mprograms_node_failure_keeps_canonical_byte_identical(tmp_path):
    class Flaky(DailyFakeClient):
        def __init__(self):
            super().__init__()
            self.raising = "AV9"

    data = tmp_path / "data"
    clock = Clock(dt.datetime(2026, 9, 26, 6, 0, tzinfo=TAIPEI))
    runs = []
    for name, factory in (("1", DailyFakeClient), ("2", Flaky)):
        checkout = tmp_path / f"checkout-{name}"
        if (data / "canonical").exists():
            shutil.copytree(data / "canonical", checkout / "canonical")
        stage = tmp_path / f"stage-{name}"
        pipeline.run("daily", ["mprograms"], [T], checkout, stage, ctx=_ctx(checkout, clock, factory))
        runs.append(merge_fetch_output(stage, data))
        if name == "1":
            before = _head(data, f"{T}/mprograms.json")
    assert _head(data, f"{T}/mprograms.json") == before
    assert runs[1].partial[0]["carried_forward"] == [{"program": "AV9"}]
    assert runs[1].applied[0]["changed"] is False
