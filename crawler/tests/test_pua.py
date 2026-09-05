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
    (0xE005, "綉"),   # 2026-09 補
    (0xE00F, "琮"),
    (0xE010, "堃"),   # 2026-09 補
    (0xE011, "豐"),
    (0xE016, "敘"),   # 2026-09 補：GServer 字形為「敍」，正規化為通用字
    (0xE017, "況"),   # 2026-09 補：GServer 字形為「况」，正規化為通用字
    (0xE019, "鑛"),   # 2026-09 r2
    (0xE026, "炯"),
    (0xE02E, "暐"),
    (0xE031, "凃"),
    (0xE034, "烟"),
    (0xE03C, "烜"),   # 2026-09 補
    (0xE03F, "羣"),
    (0xE041, "稜"),
    (0xE043, "霙"),
    (0xE046, "煒"),
    (0xE049, "湉"),
    (0xE04D, "晧"),
    (0xE04F, "婕"),
    (0xE053, "珺"),   # 2026-09 補：GServer 字形 + 遠流譯者楊祖珺
    (0xE054, "栢"),
    (0xE055, "葳"),
    (0xE058, "媜"),   # 2026-09 補：GServer 字形（右旁貞非真）+ 印刻作者簡媜
    (0xE05F, "瀞"),   # 2026-09 補
    (0xE062, "献"),   # 2026-09 補
    (0xE065, "鋒"),
    (0xE069, "參"),   # 2026-09 r2：字形為「叁」，正規化為通用字
    (0xE06E, "玎"),
    (0xE077, "姵"),
    (0xE079, "數"),   # 2026-09 r2：字形為「数」，正規化為通用字
    (0xE07C, "銹"),
    (0xE081, "庄"),   # 2026-09 補
    (0xE082, "芃"),
    (0xE08F, "双"),
    (0xE098, "瑢"),
    (0xE0A5, "焄"),   # 2026-09 r2
    (0xE0AF, "溫"),
    (0xE0B2, "勳"),
    (0xE0BF, "參"),
    (0xE0C8, "運"),   # 2026-09 r2：字形為「运」，正規化為通用字
    (0xE0CD, "坂"),   # 2026-09 補
    (0xE0E1, "勳"),
    (0xE0E3, "烱"),   # 2026-09 補
    (0xE0E9, "酶"),
    (0xE0EA, "玨"),   # 2026-09 補
    (0xE0F1, "槺"),   # 2026-09 補
    (0xE0F3, "聿"),   # 2026-09 補
    (0xE101, "蔻"),
    (0xE102, "免"),
    (0xE10A, "肽"),
    (0xE10C, "胜"),
    (0xE10D, "苷"),
    (0xE11A, "館"),   # 2026-09 補
    (0xE122, "憙"),   # 2026-09 補
    (0xE12F, "祐"),
    (0xE136, "禎"),
    (0xE15C, "腳"),   # 2026-09 補：GServer 字形為「脚」，正規化為通用字
    (0xE17A, "个"),   # 2026-09 補
    (0xE188, "塲"),
    (0xE195, "熺"),
    (0xE19C, "瑤"),   # 2026-09 補
    (0xE19D, "菓"),   # 2026-09 r2
    (0xE19E, "庙"),   # 2026-09 補
    (0xE1B3, "廸"),
    (0xE1B7, "姉"),
    (0xE1D1, "棊"),   # 2026-09 補
    (0xE1DA, "啓"),
    (0xE1EB, "爲"),
    (0xE1EC, "腈"),   # 2026-09 補
    (0xE1F4, "暳"),   # 2026-09 補
    (0xE202, "強"),   # 2026-09 補
    (0xE26C, "晣"),
])
def test_pua_map_matches_gserver_glyphs(cp, want):
    # 全 73 個學校造字對照（2026-09 補 E053 珺 / E058 媜 + 本批 23 碼）
    # （GServer 採收＋使用者考證修正 E031/E10D/E0E1、正規化 E016/E017/E15C）；
    # 見 docs/research/2026-07-20-pua-glyph-verification.md
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


# ── 2026-09 補：Wingdings 批次（字形取自系統 Wingdings.ttf，非查表推測）──

@pytest.mark.parametrize("cp, want", [
    (0xF081, "①"), (0xF082, "②"), (0xF083, "③"), (0xF084, "④"), (0xF085, "⑤"),
    (0xF086, "⑥"), (0xF087, "⑦"), (0xF088, "⑧"), (0xF089, "⑨"), (0xF08A, "⑩"),
    (0xF09E, "●"), (0xF0A2, "○"), (0xF0A7, "▪"), (0xF0E0, "➔"),
])
def test_wingdings_symbols_keep_meaning(cp, want):
    # 有語意的符號（編號、項目符號、箭頭）保留成對應 Unicode 字元
    assert PUA_MAP[cp] == want
    assert normalize_pua(f"前{chr(cp)}後") == f"前{want}後"


@pytest.mark.parametrize("cp", [0xF020, 0xF052, 0xF070, 0xF071, 0xF07E,
                               0xF02A, 0xF099, 0xF0B7])
def test_wingdings_layout_glyphs_become_space(cp):
    # 條列裝飾方框/太陽/裝飾引號：不帶語意但佔位 → 空格（保住原有縮排結構）
    assert PUA_MAP[cp] == " "
    assert normalize_pua(f"前{chr(cp)}後") == "前 後"


@pytest.mark.parametrize("cp", [0xF024, 0xF0B2])
def test_wingdings_pure_decoration_is_deleted(cp):
    # 放大鏡/花飾：純裝飾且不佔語意位置 → 刪除（U+F024 在 "technology▨." 這種句中位置，
    # 換成空格會變成 "technology ." 反而更糟）
    assert PUA_MAP[cp] == ""
    assert normalize_pua(f"前{chr(cp)}後") == "前後"


def test_wingdings_book_uses_covered_codepoint():
    # U+1F56E 是 Unicode 對 Wingdings 0x26 的官方對應，但實測無字型覆蓋、畫出來仍空白，
    # 故改用覆蓋完整的 U+1F4D6；換一個同樣畫不出來的碼位等於沒修。
    assert PUA_MAP[0xF026] == "\U0001F4D6"
    assert "\U0001F56E" not in PUA_MAP.values()


def test_real_syllabus_line_from_school_page():
    # 「研究方法」(snum=298920) 第 8 週原文：&#61569;/&#61570; 即 U+F081/U+F082
    src = "圖書館資源分享：\uf081圖書館學術資源；\uf082美加地區碩博士論文"
    assert normalize_pua(src) == "圖書館資源分享：①圖書館學術資源；②美加地區碩博士論文"


def test_build_v1_carries_non_bmp_replacement(tmp_path):
    # 0xF026 → 📖 是唯一的非 BMP 目標字。production 的正規化跑在**序列化後的 JSON 字串**上
    # （artifacts._write_v1_json → normalize_pua），非 BMP 若被 \\u 代理對轉義就會替換失敗，
    # 故鎖定端到端行為。
    d = tmp_path / "canonical" / "115-1"
    d.mkdir(parents=True)
    course = CourseOffering(
        term_key="115-1", offering_id="1", name=LocalizedText(zh="測試"),
        notes_raw="第一章 參考書 甲",
        selection=Selection(cwish_subj="1"),
    )
    (d / "catalog.ndjson").write_text(course.model_dump_json() + "\n", encoding="utf-8")
    (d / "classes.json").write_text(
        ClassDirectory(term_key="115-1").model_dump_json(), encoding="utf-8"
    )
    build_v1(tmp_path, "2026-09-05T00:00:00+08:00")

    text = (tmp_path / "v1" / "terms" / "115-1" / "catalog.json").read_text(encoding="utf-8")
    assert "\\u" not in text
    assert json.loads(text)["courses"][0]["notes_raw"] == "第一章\U0001F4D6 參考書① 甲"
    TermCatalog.model_validate_json(text)
