"""matric 升級欄位：權威對照表、多碼選取規則、離線重算（rematric）。"""
import json
from pathlib import Path

from models import (
    CourseOffering,
    LocalizedText,
    MATRIC_LABELS,
    MatricSystem,
    Selection,
    select_matric_division,
)
from ntut_catalog.rematric import rematric_canonical


# -------------------------------------------------------- 權威對照表

def test_mapping_covers_all_query_curr_page_codes():
    """13 個 QueryCurrPage 下拉碼（= client.ALL_MATRIC_CODES）全在對照表。"""
    from ntut_catalog.client import ALL_MATRIC_CODES
    assert set(MATRIC_LABELS) == set(ALL_MATRIC_CODES)


def test_mapping_labels_and_systems():
    """逐碼中文標籤 + 體系（權威，來自 QueryCurrPage 下拉）。"""
    expected = {
        "5": ("日五專", MatricSystem.day),
        "6": ("日二技", MatricSystem.day),
        "7": ("日四技", MatricSystem.day),
        "8": ("碩士", MatricSystem.day),
        "9": ("博士", MatricSystem.day),
        "0": ("進修學院二技", MatricSystem.extension),
        "4": ("進修部二技", MatricSystem.extension),
        "F": ("進修部四技", MatricSystem.extension),
        "A": ("進修部碩士在職專班", MatricSystem.on_job),
        "C": ("週末碩士", MatricSystem.on_job),
        "D": ("EMBA", MatricSystem.on_job),
        "1": ("學程", MatricSystem.other),
        "E": ("學士後學位學程", MatricSystem.other),
    }
    for code, (label, system) in expected.items():
        d = MATRIC_LABELS[code]
        assert d.code == code
        assert d.label == label
        assert d.system == system


# -------------------------------------------------------- 單碼選取

def test_select_single_code():
    d = select_matric_division({"A"})
    assert d.code == "A"
    assert d.label == "進修部碩士在職專班"
    assert d.system == MatricSystem.on_job


def test_select_empty_is_none():
    assert select_matric_division(set()) is None


def test_select_unknown_code_falls_back_to_other_without_label():
    """未知碼不亂猜：system=other、label=原碼、不回退預設。"""
    d = select_matric_division({"Z"})
    assert d.code == "Z"
    assert d.label == "Z"
    assert d.system == MatricSystem.other


# -------------------------------------------------------- 多碼選取規則（確定性）

def test_select_multi_code_prefers_day_system():
    """day > extension > on_job > other：含 7(day) + A(on_job) → 取 day。"""
    d = select_matric_division({"7", "A"})
    assert d.system == MatricSystem.day
    assert d.code == "7"


def test_select_multi_code_within_system_picks_lexicographically_smallest():
    """同 day 體系內 {7,8,9} → 取字典序最小碼 7（確定且可重現）。"""
    d = select_matric_division({"9", "8", "7"})
    assert d.code == "7"


def test_select_multi_code_extension_over_on_job_and_other():
    """extension(4) 優於 on_job(A) 與 other(1)。"""
    d = select_matric_division({"1", "A", "4"})
    assert d.system == MatricSystem.extension
    assert d.code == "4"


def test_select_known_beats_unknown():
    """已知碼優先於未知碼（不被未知碼污染）。"""
    d = select_matric_division({"Z", "A"})
    assert d.code == "A"
    assert d.system == MatricSystem.on_job


def test_select_is_deterministic_regardless_of_set_order():
    codes = {"7", "8", "9", "A", "4"}
    first = select_matric_division(codes)
    second = select_matric_division(set(list(codes)[::-1]))
    assert first == second
    assert first.code == "7"  # day 體系、字典序最小


# -------------------------------------------------------- 離線重算 rematric

def _course(oid: str, matric_raw: str) -> CourseOffering:
    return CourseOffering(
        term_key="115-1", offering_id=oid, name=LocalizedText(zh="x"),
        selection=Selection(cwish_subj=oid),
        raw_fields={"matric_codes": matric_raw} if matric_raw else {},
    )


def test_rematric_promotes_codes_and_division(tmp_path):
    """A（在職碩專班）原本 matric_codes 空、matric_division None → 回算後升為第一級。"""
    d = tmp_path / "canonical" / "115-1"
    d.mkdir(parents=True)
    c = _course("365061", "A")
    (d / "catalog.ndjson").write_text(c.model_dump_json() + "\n", encoding="utf-8")

    stats = rematric_canonical(tmp_path)
    assert stats[0] == {"term": "115-1", "courses": 1, "rematriced": 1}

    out = json.loads((d / "catalog.ndjson").read_text().splitlines()[0])
    assert out["matric_codes"] == ["A"]
    assert out["matric_division"]["code"] == "A"
    assert out["matric_division"]["label"] == "進修部碩士在職專班"
    assert out["matric_division"]["system"] == "on_job"


def test_rematric_round_trips_other_fields(tmp_path):
    """只動 matric_*，其餘欄位 byte-for-byte 還原（除新欄位差異外不動）。"""
    d = tmp_path / "canonical" / "115-1"
    d.mkdir(parents=True)
    c = _course("300001", "7")
    # 先把新欄位填好（模擬已重算過的資料）→ 重算應無變更、且整列 round-trip 不變
    c.matric_codes = ["7"]
    c.matric_division = select_matric_division({"7"})
    original = c.model_dump_json(exclude_none=False)
    (d / "catalog.ndjson").write_text(original + "\n", encoding="utf-8")

    stats = rematric_canonical(tmp_path)
    assert stats[0]["rematriced"] == 0  # idempotent
    assert (d / "catalog.ndjson").read_text().strip() == original


def test_rematric_multi_code_and_no_codes(tmp_path):
    d = tmp_path / "canonical" / "115-1"
    d.mkdir(parents=True)
    multi = _course("300002", "A,7")          # 多碼 → day 優先（7）
    none = _course("300003", "")              # 無碼 → None
    (d / "catalog.ndjson").write_text(
        multi.model_dump_json() + "\n" + none.model_dump_json() + "\n", encoding="utf-8")

    rematric_canonical(tmp_path)
    lines = (d / "catalog.ndjson").read_text().splitlines()
    a = json.loads(lines[0])
    b = json.loads(lines[1])
    assert a["matric_codes"] == ["7", "A"]
    assert a["matric_division"]["code"] == "7"
    assert a["matric_division"]["system"] == "day"
    assert b["matric_codes"] == []
    assert b["matric_division"] is None
