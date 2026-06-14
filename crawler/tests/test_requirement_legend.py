from models import RequirementCategory
from ntut_catalog.requirement_legend import build_requirement


def test_required_symbols():
    for sym in ["○", "△", "●", "▲"]:
        r = build_requirement(sym)
        assert r.symbol == sym
        assert r.category == RequirementCategory.required, sym
        assert r.label_zh  # 詳細類別有值


def test_elective_symbols():
    for sym in ["☆", "★"]:
        r = build_requirement(sym)
        assert r.category == RequirementCategory.elective, sym


def test_labels():
    assert build_requirement("○").label_zh == "部訂共同必修"
    assert build_requirement("★").label_zh == "專業選修"


def test_unknown_symbol():
    assert build_requirement("?").category == RequirementCategory.unknown
    assert build_requirement(None).category == RequirementCategory.unknown
    assert build_requirement(None).symbol is None
