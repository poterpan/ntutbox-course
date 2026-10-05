"""測試用假 client 與 sample TermResult 建構（多個 test 模組共用）。"""
from pathlib import Path

from ntut_catalog.client import ALL_UNITS, SCHOOL_MATRIC
from ntut_catalog.orchestrator import crawl_term

FIXTURES = Path(__file__).parent / "fixtures"

EMPTY_TABLE = """<HTML><body><TABLE border=1><TR>
<TH>課號</TH><TH>課程名稱</TH><TH>階段</TH><TH>學分</TH><TH>時數</TH><TH>修</TH>
<TH>班級</TH><TH>教師</TH><TH>日</TH><TH>一</TH><TH>二</TH><TH>三</TH><TH>四</TH>
<TH>五</TH><TH>六</TH><TH>教室</TH><TH>人</TH><TH>撤</TH><TH>授課語言</TH>
<TH>教學大綱與進度表</TH><TH>備註</TH><TH>隨班附讀</TH><TH>實驗實習</TH><TH>跨領域</TH>
</TR></TABLE></body></HTML>"""

SUBJ2_ONE_DEPT = (
    '<html><body><a href="Subj.jsp?format=-3&year=114&sem=1&code=59">資工系</a></body></html>'
)


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

    def query_course(self, year, sem, matric, unit, **kw):
        if unit == "59" and matric == SCHOOL_MATRIC:
            return self.csie
        if unit == ALL_UNITS and matric == SCHOOL_MATRIC:
            return self.csie  # 全校一次查：只有一個系所，等於該系所的課
        if unit == ALL_UNITS and matric == "'7'":
            return self.csie  # 假設全部都是四技課
        return EMPTY_TABLE


def build_sample_result(term_key="115-1", observed_at="2026-06-13T00:00:00+08:00"):
    return crawl_term(FakeClient(), term_key, observed_at)


def record_enrollment(out_dir, term_key, enrollment, observed_at="2026-06-13T00:00:00+08:00"):
    """測試用：等同 merge 對一次人數觀測做的事（去重寫快照＋追加觀測紀錄）。"""
    from ntut_catalog import enrollment_store
    term_dir = Path(out_dir) / "canonical" / term_key
    name, _ = enrollment_store.write_snapshot(
        term_dir, enrollment_store.rows_from_enrollment(enrollment), observed_at)
    enrollment_store.append_observation(term_dir, observed_at, name)
    return name


# ============================================================ 校園 CDN（campus_gis，D28）

FAKE_GIS_ROOMS = {
    "source": {"description": "ntutbox-campus 由學校公開 GeoServer WFS 產出，勿手改", "update_sequence": 1146},
    "buildings": [
        {"aliases": ["第一教學大樓"], "building_id": "A1T", "floor_ids": ["1F"], "label": "第一教學大樓",
         "name": "第一教學大樓", "order": 10},
        {"aliases": ["宏裕科技研究大樓"], "building_id": "HR", "floor_ids": ["2F"], "label": "宏裕科研大樓",
         "name": "宏裕科技研究大樓", "order": 70},
        {"aliases": ["綜合科館"], "building_id": "CB", "floor_ids": ["B1", "1F"], "label": "綜合科館",
         "name": "綜合科館", "order": 90},
        {"aliases": ["紅樓"], "building_id": "RB", "floor_ids": ["1F"], "name": "紅樓"},
    ],
    "rooms": [
        {"building_id": "A1T", "class_number": "101", "floor_id": "1F", "name": "多元功能教室", "use": "多元功能教室"},
        {"building_id": "CB", "class_number": "B19", "floor_id": "B1", "name": "第二演講廳", "use": "第二演講廳"},
        {"building_id": "HR", "class_number": "231", "floor_id": "2F", "name": "教室", "use": None},
    ],
}


class FakeCampusClient:
    """ntutbox-campus CDN 的假 client：`files` 是 path → bytes；記錄請求過的 path。"""

    def __init__(self, gis_rooms=None, revision=2, manifest="manifest.0123456789ab.json",
                 sha256=None, schema_version=1, include_gis=True):
        from ntut_catalog.room_gis import dump_gis_rooms
        import hashlib
        import json as _json
        raw = dump_gis_rooms(gis_rooms or FAKE_GIS_ROOMS).encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        path = f"gis-rooms.{digest[:12]}.json"
        files = {"gis-rooms.json": {"path": path, "sha256": sha256 or digest, "bytes": len(raw)}} \
            if include_gis else {}
        self.files = {
            "current.json": _json.dumps({"manifest": manifest, "revision": revision,
                                         "schema_version": schema_version,
                                         "update_sequence": 1146}).encode(),
            manifest: _json.dumps({"schema_version": schema_version, "files": files}).encode(),
            path: raw,
        }
        self.requests = []
        self.digest = digest

    def get_bytes(self, path):
        self.requests.append(path)
        return self.files[path]

    def get_json(self, path):
        import json as _json
        return _json.loads(self.get_bytes(path))

    def close(self):
        pass
