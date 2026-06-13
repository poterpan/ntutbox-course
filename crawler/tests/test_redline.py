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
