import json
from pathlib import Path

from models import CourseOffering, LocalizedText, Requirement, RequirementCategory, Selection
from ntut_catalog.reprocess import (
    migrate_detail_line, migrate_details_canonical, recategorize_canonical)


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


# ---------------------------------------------------------- details 形狀遷移

def _detail_line(**syl) -> str:
    """一行 details.ndjson（手寫 JSON，刻意不經過 models——要模擬「舊 schema 寫出來的檔」。）"""
    base = {"teacher_code": "1", "teacher_name": "王", "flex_learning": {}, "extra": {}}
    base.update(syl)
    return json.dumps({"term_key": "115-1", "offering_id": "300001", "course_code": None,
                       "name": {"zh": "x", "en": None}, "description": {"zh": None, "en": None},
                       "syllabi": [base], "generated_at": None},
                      ensure_ascii=False, separators=(",", ":"))


def _syl(line: str) -> dict:
    return json.loads(line)["syllabi"][0]


def test_migrate_detail_line_converts_dict_to_ordered_array():
    line = _detail_line(flex_learning={"類別": "線上", "時數(小時)": "4", "學習成果": "…"})
    out, changed = migrate_detail_line(line)
    assert changed == 1
    assert _syl(out)["flex_learning"] == [
        {"label": "類別", "value": "線上"},
        {"label": "時數(小時)", "value": "4"},
        {"label": "學習成果", "value": "…"},
    ]


def test_migrate_detail_line_converts_empty_dict_to_empty_array():
    """舊學期（110-1～114-2）全部是 `{}`。`{}` 與 `[]` 對 Swift 的 Codable 是不同型別，
    嚴格 decoder 會整筆解碼失敗——所以「反正是空的」不能當作不用遷移的理由。"""
    out, changed = migrate_detail_line(_detail_line())
    assert changed == 1
    assert _syl(out)["flex_learning"] == [] and _syl(out)["extra"] == []


def test_migrate_detail_line_is_idempotent():
    once, _ = migrate_detail_line(_detail_line(flex_learning={"類別": "線上"}))
    twice, changed = migrate_detail_line(once)
    assert changed == 0
    assert twice == once, "已是新形狀就原樣輸出，重跑不該再動檔案"


def test_migrate_detail_line_keeps_fields_this_schema_does_not_know():
    """`Syllabus` 沒有 extra=\"forbid\"，未知欄位進 model 會被忽略、dump 時被丟掉。
    data branch 上的 115-1 已經有尚未併進 main 的 `weekly_progress`——
    遷移若走 Pydantic round-trip 就會**靜默刪掉 2,725 行的那個欄位**。
    所以只准動 flex_learning/extra 兩個 key。"""
    line = _detail_line(flex_learning={"類別": "線上"},
                        weekly_progress=[{"week": 1, "text": "課程介紹"}])
    out, _ = migrate_detail_line(line)
    assert _syl(out)["weekly_progress"] == [{"week": 1, "text": "課程介紹"}]


def test_migrate_details_canonical_rewrites_only_matching_terms(tmp_path):
    for term in ("114-2", "115-1"):
        d = tmp_path / "canonical" / term
        d.mkdir(parents=True)
        (d / "details.ndjson").write_text(
            _detail_line(flex_learning={"類別": "線上"}) + "\n", encoding="utf-8")
    stats = migrate_details_canonical(tmp_path, terms=["115-1"])
    assert [s["term"] for s in stats] == ["115-1"]
    assert _syl((tmp_path / "canonical" / "115-1" / "details.ndjson").read_text())["flex_learning"] \
        == [{"label": "類別", "value": "線上"}]
    assert _syl((tmp_path / "canonical" / "114-2" / "details.ndjson").read_text())["flex_learning"] \
        == {"類別": "線上"}, "沒指定的學期不該被動到"


def test_migrate_details_canonical_defaults_to_every_term(tmp_path):
    for term in ("114-2", "115-1"):
        d = tmp_path / "canonical" / term
        d.mkdir(parents=True)
        (d / "details.ndjson").write_text(_detail_line() + "\n", encoding="utf-8")
    stats = migrate_details_canonical(tmp_path)
    assert sorted(s["term"] for s in stats) == ["114-2", "115-1"]
    assert all(s["syllabi_migrated"] == 1 for s in stats)
