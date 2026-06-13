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

    def query_course(self, year, sem, matric, unit):
        if unit == "59" and matric == SCHOOL_MATRIC:
            return self.csie
        if unit == ALL_UNITS and matric == "'7'":
            return self.csie  # 假設全部都是四技課
        return EMPTY_TABLE


def build_sample_result(term_key="115-1", observed_at="2026-06-13T00:00:00+08:00"):
    return crawl_term(FakeClient(), term_key, observed_at)
