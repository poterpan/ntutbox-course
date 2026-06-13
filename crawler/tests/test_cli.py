from ntut_catalog.cli import expand_terms


def test_expand_range():
    assert expand_terms("110-1:115-1") == [
        "110-1", "110-2", "111-1", "111-2", "112-1", "112-2",
        "113-1", "113-2", "114-1", "114-2", "115-1",
    ]


def test_expand_single_and_list():
    assert expand_terms("114-1") == ["114-1"]
    assert expand_terms("114-1,114-2") == ["114-1", "114-2"]
    assert expand_terms("114-2:115-1") == ["114-2", "115-1"]
