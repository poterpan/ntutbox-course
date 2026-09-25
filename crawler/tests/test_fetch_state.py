"""fetch-state：checked_at／changed_at／content_sha256 的更新規則（spec §1）。"""
from ntut_catalog import fetch_state as fs


def test_hash_unchanged_only_moves_checked_at():
    s = fs.empty()
    assert fs.update(s, "catalog", "115-1", "h1", "2026-09-26T06:00:00+08:00") is True
    assert fs.update(s, "catalog", "115-1", "h1", "2026-09-27T06:00:00+08:00") is False
    assert fs.get(s, "catalog", "115-1") == {"checked_at": "2026-09-27T06:00:00+08:00",
                                             "changed_at": "2026-09-26T06:00:00+08:00",
                                             "content_sha256": "h1"}
    assert fs.update(s, "catalog", "115-1", "h2", "2026-09-28T06:00:00+08:00") is True
    assert fs.get(s, "catalog", "115-1")["changed_at"] == "2026-09-28T06:00:00+08:00"


def test_checked_at_never_moves_backwards():
    """過期 checkout 的 run 較晚進鎖，帶的是較早的 checked_at。"""
    s = fs.empty()
    fs.update(s, "catalog", "115-1", "h1", "2026-09-26T10:00:00+08:00")
    fs.update(s, "catalog", "115-1", "h1", "2026-09-26T09:58:00+08:00")
    assert fs.get(s, "catalog", "115-1")["checked_at"] == "2026-09-26T10:00:00+08:00"


def test_keys_are_independent_and_global_key(tmp_path):
    s = fs.empty()
    fs.update(s, "catalog", "115-1", "a", "2026-09-26T06:00:00+08:00")
    fs.update(s, "catalog", "114-2", "b", "2026-09-25T06:00:00+08:00")
    fs.update(s, "calendar", None, "c", "2026-09-26T06:00:00+08:00")
    path = fs.path_for(tmp_path)
    fs.save(path, s)
    loaded = fs.load(path)
    assert set(loaded["datasets"]["catalog"]) == {"115-1", "114-2"}
    assert set(loaded["datasets"]["calendar"]) == {"_global"}
    assert path == tmp_path / "_meta" / "fetch-state.json"
    assert fs.load(tmp_path / "missing.json") == fs.empty()


def test_content_hash_depends_on_bytes_and_file_set(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text("1", encoding="utf-8")
    b.write_text("2", encoding="utf-8")
    h = fs.content_hash([a, b], tmp_path)
    assert h == fs.content_hash([b, a], tmp_path)         # 與輸入順序無關
    assert h != fs.content_hash([a], tmp_path)             # 檔案少一個也算改變
    b.write_text("3", encoding="utf-8")
    assert h != fs.content_hash([a, b], tmp_path)
