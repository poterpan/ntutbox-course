from pathlib import Path

from ntut_catalog.programs import crawl_mprograms, crawl_standards

FIXTURES = Path(__file__).parent / "fixtures"


class FakeProgClient:
    def __init__(self, broken=None):
        self.mlist = (FIXTURES / "mprogram_list_115-1.html").read_text(encoding="utf-8")
        self.mdetail = (FIXTURES / "mprogram_AV9.html").read_text(encoding="utf-8")
        self.cmatric = (FIXTURES / "cprog_-2_115.html").read_text(encoding="utf-8")
        self.cdiv = (FIXTURES / "cprog_-3_115_7.html").read_text(encoding="utf-8")
        self.cleaf = (FIXTURES / "cprog_-4_sample.html").read_text(encoding="utf-8")
        self.mprog_leaf = (FIXTURES / "cprog_-4_mprogram_av2.html").read_text(encoding="utf-8")
        self.broken = broken  # 該 division 的 cprog -4/matric=H 回錯誤頁

    def mprogram_list(self, year, sem):
        return self.mlist

    def mprogram(self, year, sem, code):
        return self.mdetail

    def cprog(self, format, **p):
        # 微學程課程標準：cprog -4/matric=H，所有學程碼都回 AV2 課標 fixture
        if format == "-4" and p.get("matric") == "H":
            if self.broken is not None and p.get("division") == self.broken:
                return "<html>查無資料</html>"
            return self.mprog_leaf
        # 既有系所課程標準對照（-2/-3/-4）維持原樣
        return {"-2": self.cmatric, "-3": self.cdiv, "-4": self.cleaf}[format]


def test_crawl_mprograms():
    d = crawl_mprograms(FakeProgClient(), "115-1")
    assert d.term_key == "115-1"
    assert len(d.programs) >= 40
    av9 = next(p for p in d.programs if p.code == "AV9")
    assert av9.name == "人工智慧與深度學習微學程"
    assert len(av9.offering_ids) == 22       # 該學程 22 門開課


def test_crawl_mprograms_enriched():
    d = crawl_mprograms(FakeProgClient(), "115-1")
    p = d.programs[0]
    assert p.code == "AV2"
    assert len(p.courses) == 27                       # AV2 fixture 課程數
    assert {c.category for c in p.courses} == {"基礎", "核心", "總整"}
    assert p.rules_text and "微學程設置定義" in p.rules_text
    assert all(c.course_code for c in p.courses)
    # offering_ids 仍來自 mprogram 開課清單、與課程標準無關
    assert p.offering_ids == crawl_mprograms(FakeProgClient(), "115-1").programs[0].offering_ids


def test_crawl_mprograms_broken_program_isolated():
    """單一學程課標抓取失敗 → 該學程 courses=[]/rules_text=None，其餘正常、整體不拋。"""
    d = crawl_mprograms(FakeProgClient(broken="AV9"), "115-1")
    av9 = next(p for p in d.programs if p.code == "AV9")
    assert av9.courses == []
    assert av9.rules_text is None
    # 其餘學程仍正常 enrich
    healthy = next(p for p in d.programs if p.code != "AV9")
    assert len(healthy.courses) == 27
    assert healthy.rules_text is not None


def test_crawl_standards():
    d = crawl_standards(FakeProgClient(), 115)
    assert d.entry_year == 115
    assert len(d.programs) >= 1               # 每個 division 都回同一葉(fake)
    p = d.programs[0]
    assert p.entry_year == 115
    assert len(p.courses) >= 5
    assert any(c.course_code == "1410045" for c in p.courses)
