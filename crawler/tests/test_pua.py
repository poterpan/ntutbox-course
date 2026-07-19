"""PUA 正規化：normalize_pua / normalize_pua_obj 單元 + build_v1 整合。"""
import json

import pytest

from models import (
    ClassDirectory,
    CourseDetail,
    CourseOffering,
    LocalizedText,
    MicroProgram,
    MicroProgramDirectory,
    Selection,
    Syllabus,
    TermCatalog,
)
from ntut_catalog.artifacts import build_v1
from ntut_catalog.pua import PUA_MAP, normalize_pua, normalize_pua_obj

# 具名 PUA 碼位（測試可讀）
F0D8 = ""   # Wingdings 0xD8 → ➢
F0FC = ""   # Wingdings 0xFC → ✓
F0B1 = ""   # Symbol 0xB1 → ±
E1B3 = ""   # 學校造字 → 廸
EUNK = "\uef0d"  # PUA 無字形碼位（GServer 造字庫無輪廓、故不入表）→ 原樣保留；見 docs/research/2026-07-20-pua-glyph-verification.md §4.2


# ── normalize_pua 單元 ──

def test_maps_verified_wingdings_bullet():
    assert normalize_pua(f"{F0D8}\t封面") == "➢\t封面"


def test_maps_checkmark_and_school_glyph():
    assert normalize_pua(F0FC) == "✓"
    assert normalize_pua(f"林{E1B3}") == "林廸"


@pytest.mark.parametrize("cp, want", [
    (0xE001, "峯"),
    (0xE00F, "琮"),
    (0xE011, "豐"),
    (0xE026, "炯"),
    (0xE02E, "暐"),
    (0xE031, "凃"),
    (0xE034, "烟"),
    (0xE03F, "羣"),
    (0xE041, "稜"),
    (0xE043, "霙"),
    (0xE046, "煒"),
    (0xE049, "湉"),
    (0xE04D, "晧"),
    (0xE04F, "婕"),
    (0xE054, "栢"),
    (0xE055, "葳"),
    (0xE065, "鋒"),
    (0xE06E, "玎"),
    (0xE077, "姵"),
    (0xE07C, "銹"),
    (0xE082, "芃"),
    (0xE08F, "双"),
    (0xE098, "瑢"),
    (0xE0AF, "溫"),
    (0xE0B2, "勳"),
    (0xE0BF, "參"),
    (0xE0E1, "勳"),
    (0xE0E9, "酶"),
    (0xE101, "蔻"),
    (0xE102, "免"),
    (0xE10A, "肽"),
    (0xE10C, "胜"),
    (0xE10D, "苷"),
    (0xE12F, "祐"),
    (0xE136, "禎"),
    (0xE188, "塲"),
    (0xE195, "熺"),
    (0xE1B3, "廸"),
    (0xE1B7, "姉"),
    (0xE1DA, "啓"),
    (0xE1EB, "爲"),
    (0xE26C, "晣"),
])
def test_pua_map_matches_gserver_glyphs(cp, want):
    # 全 42 個學校造字對照（GServer 採收＋使用者考證修正 E031/E10D/E0E1）；見 docs/research/2026-07-20-pua-glyph-verification.md
    assert PUA_MAP[cp] == want
    assert normalize_pua(f"林{chr(cp)}") == f"林{want}"


def test_symbol_exception_plus_minus():
    # 0xB1 唯一出現在算式括號內、非條列 → 取 Symbol ± 而非 Wingdings 位置標記
    assert normalize_pua(f"平時成績({F0B1}10%)") == "平時成績(±10%)"


def test_unknown_codepoint_preserved():
    # 未考證的造字：不猜、不刪，原樣保留
    assert normalize_pua(f"某{EUNK}師") == f"某{EUNK}師"
    assert EUNK not in PUA_MAP and ord(EUNK) not in PUA_MAP


def test_mixed_string_maps_known_keeps_unknown():
    src = f"{F0D8}\t作業 林{E1B3}（{EUNK}）{F0FC}"
    assert normalize_pua(src) == f"➢\t作業 林廸（{EUNK}）✓"


def test_no_pua_returns_identical_object():
    s = "純中文 abc 123 ●■"
    assert normalize_pua(s) is s          # 快速路徑：無 PUA → 原物件


def test_empty_string():
    assert normalize_pua("") == ""


# ── normalize_pua_obj 遞迴 ──

def test_normalize_obj_recurses_dict_list_str():
    obj = {
        "a": f"林{E1B3}",
        "b": [f"{F0FC} ok", 3, None, {"c": f"{F0D8} x"}],
        "n": 42,
    }
    out = normalize_pua_obj(obj)
    assert out == {"a": "林廸", "b": ["✓ ok", 3, None, {"c": "➢ x"}], "n": 42}


def test_normalize_obj_does_not_mutate_input():
    obj = {"k": [f"林{E1B3}"]}
    normalize_pua_obj(obj)
    assert obj == {"k": [f"林{E1B3}"]}    # 原物件不變


# ── build_v1 整合：canonical 含 PUA → v1 已轉、未知保留、canonical 不動 ──

def _write_canonical_with_pua(tmp_path, term="115-1"):
    d = tmp_path / "canonical" / term
    d.mkdir(parents=True)
    course = CourseOffering(
        term_key=term,
        offering_id="300777",
        name=LocalizedText(zh=f"測試課程 林{E1B3}"),
        notes_raw=f"備註 {EUNK} 未考證造字",
        selection=Selection(cwish_subj="300777"),
    )
    (d / "catalog.ndjson").write_text(course.model_dump_json() + "\n", encoding="utf-8")
    (d / "classes.json").write_text(
        ClassDirectory(term_key=term).model_dump_json(), encoding="utf-8"
    )
    detail = CourseDetail(
        term_key=term,
        offering_id="300777",
        name=LocalizedText(zh=f"測試課程 林{E1B3}"),
        syllabi=[Syllabus(teacher_name="老師", assessment=f"{F0D8}\t期中 30%\n{F0FC} 出席")],
    )
    (d / "details.ndjson").write_text(detail.model_dump_json() + "\n", encoding="utf-8")
    mprograms = MicroProgramDirectory(
        term_key=term,
        programs=[MicroProgram(
            code="H01",
            name=f"創新學程 林{E1B3}",
            rules_text=f"相關規定：{F0FC} 至少修 9 學分 {EUNK}",
        )],
    )
    (d / "mprograms.json").write_text(mprograms.model_dump_json(), encoding="utf-8")
    return d


def test_build_v1_normalizes_catalog_and_detail(tmp_path):
    canonical = _write_canonical_with_pua(tmp_path)
    build_v1(tmp_path, "2026-07-19T00:00:00+08:00")
    t = tmp_path / "v1" / "terms" / "115-1"

    cat_text = (t / "catalog.json").read_text(encoding="utf-8")
    assert E1B3 not in cat_text and "林廸" in cat_text       # 造字已轉
    assert EUNK in cat_text                                   # 未考證造字原樣保留
    # v1 仍是合法 JSON、可回模型
    TermCatalog.model_validate_json(cat_text)

    names = json.loads((t / "names.json").read_text(encoding="utf-8"))
    assert names["300777"] == "測試課程 林廸"

    detail_text = (t / "course" / "300777.json").read_text(encoding="utf-8")
    assert F0D8 not in detail_text and F0FC not in detail_text
    # 轉出的真字都在（tab 在 JSON 被轉義成 \\t，故不比字元、只比可見字）
    assert "➢" in detail_text and "期中 30%" in detail_text and "✓ 出席" in detail_text

    # canonical 端不得被改動（分層原則）
    canon_cat = (canonical / "catalog.ndjson").read_text(encoding="utf-8")
    canon_det = (canonical / "details.ndjson").read_text(encoding="utf-8")
    assert E1B3 in canon_cat                                  # 原文忠實保留
    assert F0D8 in canon_det and F0FC in canon_det


def test_build_v1_catalog_has_no_uXXXX_escape(tmp_path):
    # 鎖定假設：序列化不 \\u 轉義，否則對文字做碼位替換會失效
    _write_canonical_with_pua(tmp_path)
    build_v1(tmp_path, "2026-07-19T00:00:00+08:00")
    cat_text = (tmp_path / "v1" / "terms" / "115-1" / "catalog.json").read_text(encoding="utf-8")
    assert "\\u" not in cat_text


def test_build_v1_normalizes_mprograms(tmp_path):
    # mprograms.json 是 canonical→v1 純文字複製；名稱/rules_text 也須經 PUA 正規化
    canonical = _write_canonical_with_pua(tmp_path)
    build_v1(tmp_path, "2026-07-19T00:00:00+08:00")
    mp_text = (tmp_path / "v1" / "terms" / "115-1" / "mprograms.json").read_text(encoding="utf-8")

    assert E1B3 not in mp_text                                # 造字已轉
    assert "創新學程 林廸" in mp_text                          # 學程名
    assert "✓ 至少修 9 學分" in mp_text                       # rules_text 內的符號
    assert EUNK in mp_text                                    # 未考證造字保留
    MicroProgramDirectory.model_validate_json(mp_text)        # 仍合法

    # canonical mprograms 不得被改動
    assert E1B3 in (canonical / "mprograms.json").read_text(encoding="utf-8")
