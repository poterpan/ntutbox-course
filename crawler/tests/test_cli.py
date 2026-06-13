from ntut_catalog.cli import expand_terms, term_already_done


def test_term_already_done_checks_canonical(tmp_path):
    assert term_already_done(tmp_path, "115-1") is False
    d = tmp_path / "canonical" / "115-1"
    d.mkdir(parents=True)
    (d / "catalog.ndjson").write_text("{}\n")
    assert term_already_done(tmp_path, "115-1") is True
    # v1 存在但 canonical 不存在 → 仍視為未完成（修正：skip 看 canonical 非 v1）
    (tmp_path / "v1" / "terms" / "114-1").mkdir(parents=True)
    assert term_already_done(tmp_path, "114-1") is False


def test_expand_range():
    assert expand_terms("110-1:115-1") == [
        "110-1", "110-2", "111-1", "111-2", "112-1", "112-2",
        "113-1", "113-2", "114-1", "114-2", "115-1",
    ]


def test_expand_single_and_list():
    assert expand_terms("114-1") == ["114-1"]
    assert expand_terms("114-1,114-2") == ["114-1", "114-2"]
    assert expand_terms("114-2:115-1") == ["114-2", "115-1"]
