"""發布端 ↔ App 的契約樣本。

`crawler/tests/fixtures/contract/*.json` 是給 iOS 端手寫 Codable 對照用的
（`docs/research/2026-09-06-course-content-and-weekly-progress-handoff.md` §7）。
樣本一律由現行 parser 產出並在這裡比對——手維護的樣本會過期，App 會照著一份
早就不存在的形狀寫 decoder。要更新：跑 `pytest -k contract --update-contract-fixtures`。
"""
import json
from pathlib import Path

from models import CourseDetail, LocalizedText
from ntut_catalog.parse_detail import parse_syllabus

FIXTURES = Path(__file__).parent / "fixtures"
CONTRACT = FIXTURES / "contract"

# 第三位教師：來源目前沒有的形狀，但 App 的 decoder 必須撐得住——
# 重複 label（同一欄拆成 17／18 兩列）與非空的 extra（校方新增未知欄位）。
_SYNTHETIC_HTML = """
<table>
  <tr><th>教師姓名</th><td>樣本教師（合成，非真實課程）</td></tr>
  <tr><th>課程大綱</th><td>合成樣本：示範重複 label 與 extra。</td></tr>
  <tr><th>校方未來新增的欄位</th><td>某個值</td></tr>
  <tr><th>彈性學習(17-18週)</th><td>
    <table class="flex-learn-table">
      <tr><th>內容</th><td>第17週：課程口試</td></tr>
      <tr><th>內容</th><td>第18週：反思報告</td></tr>
      <tr><th>時數(小時)</th><td>6</td></tr>
    </table>
  </td></tr>
</table>
"""


def _build_sample() -> CourseDetail:
    """三位教師涵蓋三種形態：有彈性學習／沒有／重複 label + extra。"""
    with_flex = parse_syllabus(
        (FIXTURES / "syllabus_360748_live.html").read_text(encoding="utf-8"), teacher_code="12567")
    without_flex = parse_syllabus(
        (FIXTURES / "syllabus_360748.html").read_text(encoding="utf-8"), teacher_code="12567")
    synthetic = parse_syllabus(_SYNTHETIC_HTML, teacher_code="99999")
    return CourseDetail(
        term_key="115-1",
        offering_id="999999",          # 佔位（見 fixtures/contract/README.md）
        course_code="2B04001",
        name=LocalizedText(zh="英語簡報技巧(一)", en="English Presentation Skills (I)"),
        description=LocalizedText(zh="契約樣本：欄位形狀才是重點，識別碼是佔位值。", en=None),
        syllabi=[with_flex, without_flex, synthetic],
    )


def test_course_detail_contract_fixture_matches_parser(pytestconfig):
    path = CONTRACT / "course-detail-115-1.json"
    expected = json.loads(_build_sample().model_dump_json())
    if pytestconfig.getoption("--update-contract-fixtures"):
        path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    actual = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected, "契約樣本與 parser 產出不一致；確認是刻意改契約後用 --update-contract-fixtures 更新"


def test_contract_fixture_covers_the_shapes_app_must_handle():
    """樣本的價值在於涵蓋度，掉了哪一種形態就等於 App 沒測到。"""
    d = json.loads((CONTRACT / "course-detail-115-1.json").read_text(encoding="utf-8"))
    flex = [s["flex_learning"] for s in d["syllabi"]]
    assert any(len(f) >= 5 for f in flex), "要有一份完整的彈性學習（五欄）"
    assert any(f == [] for f in flex), "要有一份沒有彈性學習的"
    dup = [f for f in flex if len({r["label"] for r in f}) < len(f)]
    assert dup, "要有一份含重複 label 的"
    assert any(s["extra"] for s in d["syllabi"]), "要有一份 extra 非空的"
    for s in d["syllabi"]:
        for row in s["flex_learning"] + s["extra"]:
            assert set(row) == {"label", "value"}, "每列只有 label/value"
            assert row["value"].strip(), "不變量：value 非空白"
