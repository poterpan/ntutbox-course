import json
from pathlib import Path

from models import CourseOffering, LocalizedText, Requirement, RequirementCategory, Selection
from ntut_catalog.reprocess import recategorize_canonical


def test_recategorize_fills_category(tmp_path):
    d = tmp_path / "canonical" / "115-1"
    d.mkdir(parents=True)
    # 既有：有 symbol 但 category=unknown（舊資料樣態）
    c = CourseOffering(term_key="115-1", offering_id="300001", name=LocalizedText(zh="x"),
                       selection=Selection(cwish_subj="300001"),
                       requirement=Requirement(symbol="▲", category=RequirementCategory.unknown))
    (d / "catalog.ndjson").write_text(c.model_dump_json() + "\n", encoding="utf-8")
    stats = recategorize_canonical(tmp_path)
    assert stats[0]["recategorized"] == 1
    out = json.loads((d / "catalog.ndjson").read_text().splitlines()[0])
    assert out["requirement"]["category"] == "required"
    assert out["requirement"]["label_zh"] == "校訂專業必修"
