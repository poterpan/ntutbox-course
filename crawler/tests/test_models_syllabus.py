"""Syllabus 的 v2→v3 輸入相容：pass-through 欄位讀得進舊形狀的 dict。"""
from models import CourseDetail, Syllabus


def test_syllabus_reads_v2_dict_and_normalizes_to_v3_array():
    """canonical 上還有沒遷移的學期，而 reprocess_progress 會對整份 details.ndjson
    做 Pydantic round-trip（`reprocess.py`）——model 不吃舊形狀，整條 reprocess 管線
    就會在舊學期上炸掉。讀得進來，但**寫出去一律是新形狀**。"""
    s = Syllabus.model_validate({"teacher_name": "王",
                                 "flex_learning": {"類別": "線上", "時數(小時)": "4"},
                                 "extra": {"校方新欄位": "某值"}})
    assert [(r.label, r.value) for r in s.flex_learning] == [("類別", "線上"), ("時數(小時)", "4")]
    assert [(r.label, r.value) for r in s.extra] == [("校方新欄位", "某值")]


def test_syllabus_reads_v2_empty_dict():
    """110-1～114-2 全學期都是 `{}`（彈性學習是 115 學年度才有的政策）。"""
    s = Syllabus.model_validate({"teacher_name": "王", "flex_learning": {}, "extra": {}})
    assert s.flex_learning == [] and s.extra == []


def test_v2_dict_input_round_trips_out_as_v3_array():
    """相容只在入口，出口沒有第二種形狀——否則 v2 會從舊檔一路漏到新發佈檔。"""
    d = CourseDetail.model_validate({"term_key": "115-1", "offering_id": "1",
                                     "syllabi": [{"teacher_name": "王",
                                                  "flex_learning": {"類別": "線上"}}]})
    assert '"flex_learning":[{"label":"類別","value":"線上"}]' in d.model_dump_json()


def test_v3_array_input_still_works():
    s = Syllabus.model_validate({"teacher_name": "王",
                                 "flex_learning": [{"label": "內容", "value": "第17週"},
                                                   {"label": "內容", "value": "第18週"}]})
    assert [r.value for r in s.flex_learning] == ["第17週", "第18週"], "重複 label 不因相容層而合併"
