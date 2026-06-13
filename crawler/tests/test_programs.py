from pathlib import Path

from ntut_catalog.programs import crawl_mprograms, crawl_standards

FIXTURES = Path(__file__).parent / "fixtures"


class FakeProgClient:
    def __init__(self):
        self.mlist = (FIXTURES / "mprogram_list_115-1.html").read_text(encoding="utf-8")
        self.mdetail = (FIXTURES / "mprogram_AV9.html").read_text(encoding="utf-8")
        self.cmatric = (FIXTURES / "cprog_-2_115.html").read_text(encoding="utf-8")
        self.cdiv = (FIXTURES / "cprog_-3_115_7.html").read_text(encoding="utf-8")
        self.cleaf = (FIXTURES / "cprog_-4_sample.html").read_text(encoding="utf-8")

    def mprogram_list(self, year, sem):
        return self.mlist

    def mprogram(self, year, sem, code):
        return self.mdetail

    def cprog(self, format, **p):
        return {"-2": self.cmatric, "-3": self.cdiv, "-4": self.cleaf}[format]


def test_crawl_mprograms():
    d = crawl_mprograms(FakeProgClient(), "115-1")
    assert d.term_key == "115-1"
    assert len(d.programs) >= 40
    av9 = next(p for p in d.programs if p.code == "AV9")
    assert av9.name == "人工智慧與深度學習微學程"
    assert len(av9.offering_ids) == 22       # 該學程 22 門開課


def test_crawl_standards():
    d = crawl_standards(FakeProgClient(), 115)
    assert d.entry_year == 115
    assert len(d.programs) >= 1               # 每個 division 都回同一葉(fake)
    p = d.programs[0]
    assert p.entry_year == 115
    assert len(p.courses) >= 5
    assert any(c.course_code == "1410045" for c in p.courses)
