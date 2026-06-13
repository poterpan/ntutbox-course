from pathlib import Path

from ntut_catalog.parse_subj import parse_classes, parse_departments

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_departments_114_1():
    html = (FIXTURES / "subj_-2_114-1.html").read_text(encoding="utf-8")
    depts = parse_departments(html)
    assert len(depts) == 61
    assert ("59", "資工系") in depts
    assert ("14", "通識中心") in depts
    assert ("AA", "校院級課程") in depts
    # 全部 code 唯一
    codes = [c for c, _ in depts]
    assert len(codes) == len(set(codes))


def test_parse_classes_csie_114_1():
    html = (FIXTURES / "subj_-3_114-1_59.html").read_text(encoding="utf-8")
    classes = parse_classes(html)
    assert len(classes) == 5
    assert ("3032", "資工二") in classes
    assert ("3163", "資工所") in classes


def test_no_links_returns_empty():
    """<a> 缺失 → 空清單，勿回退預設值（gnehs 教訓）。"""
    assert parse_departments("<html><body><p>無資料</p></body></html>") == []
    assert parse_classes("<html><body></body></html>") == []
