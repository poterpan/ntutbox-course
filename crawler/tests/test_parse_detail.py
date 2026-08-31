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
