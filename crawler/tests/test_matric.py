"""matric 升級欄位：權威對照表、多碼選取規則、（離線重算 rematric 已隨一次性指令刪除）。"""
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
