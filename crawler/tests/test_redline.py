from infra.redline_scan import scan_paths, scan_text


def test_scan_flags_secrets_and_error_pages():
    assert scan_text("JSESSIONID=abc123")        # session id
    assert scan_text("Set-Cookie: foo=bar")
    assert scan_text("password: 1234")
    assert scan_text("Authorization: Bearer x")
    assert scan_text("查詢選課資料出現錯誤")        # 完整錯誤頁標記
    assert scan_text("<!DOCTYPE html><html>")     # 整頁 HTML 漏入
    assert scan_text("學號 123456789")             # 9+ 位數疑似學號


def test_scan_clean_course_data_passes():
    # 課號6碼、課程編碼7碼、節次、時間戳皆不該誤判
    clean = '{"offering_id":"366392","course_code":"5904319","enrolled_count":73,' \
            '"observed_at":"2026-06-13T05:46:11+08:00","classes":[{"code":"2646"}]}'
    assert scan_text(clean) == []


def test_scan_paths(tmp_path):
    (tmp_path / "good.ndjson").write_text('{"offering_id":"300001"}\n', encoding="utf-8")
    (tmp_path / "bad.ndjson").write_text("JSESSIONID=leak\n", encoding="utf-8")
    hits = scan_paths(tmp_path)
    assert "good.ndjson" not in str(hits)
    assert any("bad.ndjson" in str(p) for p in hits)


def test_free_text_skips_student_id():
    from infra.redline_scan import scan_text
    # 自由文字（大綱）含 ISBN/電話 → 不該誤判 student-id
    assert scan_text("ISBN：9789865034146 手機：0952391961", free_text=True) == []
    # 結構化資料(free_text=False)仍擋 9+ 位數字
    assert "suspect_student_id" in scan_text("學號 123456789", free_text=False)
    # 註：本測試原本還斷言「JSESSIONID 在自由文字也要擋」。2026-09-01 起
    # details 只套 _FREE_TEXT_RULES（html_page/error_page）——爬取免登入、
    # details 無 raw_fields，session 規則在那裡只會誤判。理由見 redline_scan.py
    # 的 _FREE_TEXT_RULES 註解；結構化檔的行為由 test_structured_data_keeps_all_rules 守著。


# ── 自由文字只套真實風險的規則（2026-09-01 111-2 事件）──────────────
# 紅線掃描的原始意圖是防 raw_fields 夾帶整頁 HTML。實測 details.ndjson 沒有
# raw_fields（catalog 才有），且爬取免登入 → session/授權標頭/學號在 details
# 不可能出現，那些規則只會誤判（實績兩次）。

def test_free_text_only_applies_real_risk_rules():
    """details 只掃 html_page / error_page。"""
    # 真實案例：111-2 三門「金融資訊安全」的課程進度
    real = ("week 9 Mid-term report week 10-12 Authentication and authorization: "
            "from cryptography to application flow week 13")
    assert scan_text(real, free_text=True) == [], "課綱主題不該被當授權標頭"
    # 課綱含 ISBN / 電話（既有行為，維持）
    assert scan_text("ISBN 9789571234567 電話 0287712171", free_text=True) == []
    # 免登入抓不到、但就算字面出現也不該擋自由文字
    assert scan_text("password: 見課堂說明", free_text=True) == []


def test_free_text_still_blocks_html_and_error_page():
    """真實風險仍要擋：整頁 HTML 漏入、學校錯誤頁被當資料。"""
    assert "html_page" in scan_text("<!DOCTYPE html><html>", free_text=True)
    assert "error_page" in scan_text("查詢選課資料出現錯誤", free_text=True)


def test_structured_data_keeps_all_rules():
    """catalog/classes 等結構化檔維持全部規則——那裡有 raw_fields，
    解析失敗會夾帶原始 HTML，是紅線掃描真正要防的東西。"""
    for s, want in [
        ("Authorization: Bearer x", "authorization"),
        ("Set-Cookie: JSESSIONID=x", "session"),
        ("password: 1234", "credential"),
        ("學號 123456789", "suspect_student_id"),
    ]:
        assert want in scan_text(s, free_text=False), f"結構化檔應擋: {s!r}"
