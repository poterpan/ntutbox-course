from pathlib import Path

from ntut_catalog.parse_detail import parse_curr, parse_syllabus

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_curr():
    html = (FIXTURES / "curr_2B04001.html").read_text(encoding="utf-8")
    info = parse_curr(html)
    assert info["course_code"] == "2B04001"
    assert info["name_zh"] == "英語簡報技巧(一)"
    assert info["name_en"] == "English Presentation Skills (I)"
    assert info["description_zh"].startswith("本課程以語言教學目標")
    assert info["description_en"].startswith("This course aims to help students")


def test_parse_curr_empty_handles_missing():
    info = parse_curr("<html><body>no table</body></html>")
    assert info["name_en"] is None
    assert info["description_zh"] is None


def test_parse_syllabus():
    html = (FIXTURES / "syllabus_360748.html").read_text(encoding="utf-8")
    s = parse_syllabus(html, teacher_code="12567")
    assert s.teacher_code == "12567"
    assert s.teacher_name == "高銘宏"
    assert s.office_hours_url and "Teach.jsp" in s.office_hours_url
    assert s.email == "teacher@example.com"          # fixture 已遮蔽
    assert s.updated_at == "2026-06-04 23:35:14"
    assert s.outline.startswith("本課程以語言教學目標")
    assert "W1. Course Introduction" in s.schedule
    assert "School-Wide English Proficiency Test" in s.assessment
    assert s.materials is not None                    # 教材欄存在
    assert s.sdgs is not None                         # SDGs 欄存在
    assert s.ai_usage is not None                     # AI 欄存在
    # 不可把基本資料表的「備註(限五專學生修習)」誤當大綱欄
    assert s.outline and "限五專" not in s.outline


def test_parse_syllabus_unknown_labels_go_to_extra():
    # 來源若新增未知標籤，進 extra 不丟失
    html = (FIXTURES / "syllabus_360748.html").read_text(encoding="utf-8")
    s = parse_syllabus(html, teacher_code="12567")
    assert isinstance(s.extra, dict)


def test_parse_syllabus_tolerates_label_suffix():
    """學校 2026-08 把 <th>課程進度</th> 改成 <th>課程進度<BR>(1-16週)</th>，
    精確比對失效 → schedule 變 null、內容掉進 extra（線上 CDN 已實際壞掉）。
    標籤加後綴不該讓欄位消失。"""
    html = (FIXTURES / "syllabus_360748_live.html").read_text(encoding="utf-8")
    s = parse_syllabus(html, teacher_code="12567")
    assert s.schedule, "課程進度(1-16週) 應對映到 schedule，不該是 None"
    assert "課程進度(1-16週)" not in s.extra, "已識別的欄位不該同時留在 extra"


def test_parse_syllabus_nested_flex_table_not_mistaken_for_labels():
    """115-1 起新增 <table class="flex-learn-table">（彈性學習 17-18 週），
    嵌套 <tr> 會被 find_all("tr") 撈出來，把「類別/內容/時數(小時)/學習成果/
    評量比例」當成頂層標籤塞進 extra。"""
    html = (FIXTURES / "syllabus_360748_live.html").read_text(encoding="utf-8")
    s = parse_syllabus(html, teacher_code="12567")
    for junk in ("類別", "內容", "時數(小時)", "學習成果", "評量比例"):
        assert junk not in s.extra, f"嵌套表格的 {junk} 不該成為 extra 的 key"


def test_parse_syllabus_extracts_flex_learning_table():
    """115-1 起的「彈性學習(17-18週)」是 <table class="flex-learn-table">，
    每列 (th, td) = 欄位名/值。PR #58 為了不讓巢狀 tr 污染頂層欄位而整個跳過，
    導致這些欄位在資料層遺失（線上只剩「內容」那一欄跑進 extra）。"""
    html = (FIXTURES / "syllabus_360748_live.html").read_text(encoding="utf-8")
    s = parse_syllabus(html, teacher_code="12567")
    assert s.flex_learning, "flex-learn-table 應被解析成 key-value"
    # 欄位名跟隨來源，不寫死——只驗「有抓到多個欄位」與內容非空
    assert len(s.flex_learning) >= 2
    assert all(k and v for k, v in s.flex_learning.items())
    # 不該同時留在 extra（已被識別的區塊）
    assert "彈性學習(17-18週)" not in s.extra


def test_flex_learning_is_generic_key_value_not_fixed_schema():
    """寬容性（選 D 的核心理由）：學校改欄位名／增減欄位時不該漏抓或噴錯。
    解析器把 (th, td) 原樣存成 dict，不比對預期欄位名。"""
    html = """
    <table><tr><th>教師姓名</th><td>王小明</td></tr>
    <tr><th>彈性學習(17-18週)</th><td>
      <table class="flex-learn-table">
        <tr><th>類別</th><td>線上數位教材學習</td></tr>
        <tr><th>時數</th><td>4</td></tr>
        <tr><th>學校未來新增的欄位</th><td>某個新值</td></tr>
      </table>
    </td></tr></table>
    """
    s = parse_syllabus(html, teacher_code="x")
    assert s.flex_learning == {
        "類別": "線上數位教材學習",
        "時數": "4",                      # 改名（原「時數(小時)」）照樣抓到
        "學校未來新增的欄位": "某個新值",      # 新欄位自動吸收
    }


def test_flex_learning_absent_when_no_such_table():
    html = (FIXTURES / "syllabus_360748.html").read_text(encoding="utf-8")  # 舊 fixture 無此表
    s = parse_syllabus(html, teacher_code="12567")
    assert not s.flex_learning
