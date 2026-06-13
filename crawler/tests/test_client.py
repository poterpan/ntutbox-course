from ntut_catalog.client import ALL_MATRIC_CODES, SCHOOL_MATRIC, build_query_payload


def test_school_matric_literal():
    assert SCHOOL_MATRIC == "'0','1','4','5','6','7','8','9','A','C','D','E','F'"
    assert len(ALL_MATRIC_CODES) == 13


def test_build_query_payload():
    p = build_query_payload(114, 1, "'5'", "＊")
    assert p["year"] == "114" and p["sem"] == "1"
    assert p["matric"] == "'5'" and p["unit"] == "＊"
    assert p["stime"] == "0"                      # 缺了 server 會回錯誤頁
    assert all(p[f"D{d}"] == "ON" for d in range(7))
    assert p["PN"] == "ON" and p["P13"] == "ON"
    assert p["cname"] == "" and p["ccode"] == "" and p["tname"] == ""
