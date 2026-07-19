from pathlib import Path

from ntut_catalog.programs import crawl_mprograms, crawl_standards

FIXTURES = Path(__file__).parent / "fixtures"


class FakeProgClient:
    def __init__(self, broken=None, raising=None, mlist_html=None):
        # mlist_html：覆寫學程清單頁原始 HTML（模擬上游改版仍回 HTTP 200 但無學程連結）
        self.mlist = mlist_html if mlist_html is not None else (
            FIXTURES / "mprogram_list_115-1.html").read_text(encoding="utf-8")
        self.mdetail = (FIXTURES / "mprogram_AV9.html").read_text(encoding="utf-8")
        self.cmatric = (FIXTURES / "cprog_-2_115.html").read_text(encoding="utf-8")
        self.cdiv = (FIXTURES / "cprog_-3_115_7.html").read_text(encoding="utf-8")
        self.cleaf = (FIXTURES / "cprog_-4_sample.html").read_text(encoding="utf-8")
        self.mprog_leaf = (FIXTURES / "cprog_-4_mprogram_av2.html").read_text(encoding="utf-8")
        self.broken = broken    # 該 division 的 cprog -4/matric=H 回錯誤頁（查無資料，解析回空）
        self.raising = raising  # 該 division 的 cprog -4/matric=H 直接 raise（模擬 HTTP 500）

    def mprogram_list(self, year, sem):
        return self.mlist

    def mprogram(self, year, sem, code):
        return self.mdetail

    def cprog(self, format, **p):
        # 微學程課程標準：cprog -4/matric=H，所有學程碼都回 AV2 課標 fixture
        if format == "-4" and p.get("matric") == "H":
            div = p.get("division")
            if self.raising is not None and div == self.raising:
                raise RuntimeError("simulated 500")
            if self.broken is not None and div == self.broken:
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
    # offering_ids 仍來自 mprogram 開課清單、與課程標準無關（AV2 開課 22 門）
    assert len(p.offering_ids) == 22
    assert p.offering_ids[0] == "366392"


def test_crawl_mprograms_broken_program_isolated():
    """錯誤頁（查無資料，解析回空）→ 該學程 courses=[]/rules_text=None，其餘正常、整體不拋。"""
    d = crawl_mprograms(FakeProgClient(broken="AV9"), "115-1")
    av9 = next(p for p in d.programs if p.code == "AV9")
    assert av9.courses == []
    assert av9.rules_text is None
    assert len(av9.offering_ids) == 22            # offering_ids 不受課標失敗影響
    # 其餘學程仍正常 enrich
    healthy = next(p for p in d.programs if p.code != "AV9")
    assert len(healthy.courses) == 27
    assert healthy.rules_text is not None


def test_crawl_mprograms_cprog_raise_isolated():
    """cprog -4 直接拋例外（模擬 HTTP 500）→ 該學程降級、其餘不受影響、整個 crawl 不拋。"""
    # 若例外外洩，crawl_mprograms 這行就會拋 → 測試自然失敗
    d = crawl_mprograms(FakeProgClient(raising="AV9"), "115-1")
    av9 = next(p for p in d.programs if p.code == "AV9")
    assert av9.courses == []
    assert av9.rules_text is None
    assert len(av9.offering_ids) == 22            # offering_ids 保留
    # 其餘學程仍正常 enrich
    healthy = next(p for p in d.programs if p.code != "AV9")
    assert len(healthy.courses) == 27
    assert healthy.rules_text is not None


def test_crawl_mprograms_empty_list_raises():
    """上游改版仍回 HTTP 200 但無任何學程連結 → 拋 ValueError（含 term_key），
    避免 programs=[] 靜默覆寫並清空既有 canonical 資料。"""
    import pytest

    client = FakeProgClient(mlist_html="<html><body>改版了</body></html>")
    with pytest.raises(ValueError) as exc:
        crawl_mprograms(client, "115-1")
    assert "115-1" in str(exc.value)


def test_crawl_standards():
    d = crawl_standards(FakeProgClient(), 115)
    assert d.entry_year == 115
    assert len(d.programs) >= 1               # 每個 division 都回同一葉(fake)
    p = d.programs[0]
    assert p.entry_year == 115
    assert len(p.courses) >= 5
    assert any(c.course_code == "1410045" for c in p.courses)
