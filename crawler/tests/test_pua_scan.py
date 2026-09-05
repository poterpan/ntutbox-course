"""pua-scan：canonical 出現 PUA_MAP 未收錄的新造字碼位 → fail-loud。

掃 catalog.ndjson / details.ndjson / mprograms.json（存在才掃）；已知碼位（PUA_MAP
鍵 + KNOWN_EXCEPTIONS 例外）不算新；發現新碼位 → 列出並非零退出。
"""
import json

from models import (
    ClassDirectory,
    CourseDetail,
    CourseOffering,
    LocalizedText,
    MicroProgram,
    MicroProgramDirectory,
    Selection,
    Syllabus,
)
from ntut_catalog import cli
from ntut_catalog.pua_scan import KNOWN_EXCEPTIONS, scan_canonical

# 具名碼位
E1B3 = ""   # 已考證造字（在 PUA_MAP）→ 廸
EF0D = ""   # 壞損孤例（KNOWN_EXCEPTIONS）→ 不算新
E2FE = ""   # PUA_MAP 未收錄、非例外 → 新碼位（category Co）


def _write_term(base, term="115-1", *, name_zh="測試課程", notes="備註",
                assessment="出席 30%", mprogram_name="創新學程"):
    d = base / "canonical" / term
    d.mkdir(parents=True, exist_ok=True)
    course = CourseOffering(
        term_key=term,
        offering_id="300777",
        name=LocalizedText(zh=name_zh),
        notes_raw=notes,
        selection=Selection(cwish_subj="300777"),
    )
    (d / "catalog.ndjson").write_text(course.model_dump_json() + "\n", encoding="utf-8")
    (d / "classes.json").write_text(
        ClassDirectory(term_key=term).model_dump_json(), encoding="utf-8"
    )
    detail = CourseDetail(
        term_key=term,
        offering_id="300777",
        name=LocalizedText(zh=name_zh),
        syllabi=[Syllabus(teacher_name="老師", assessment=assessment)],
    )
    (d / "details.ndjson").write_text(detail.model_dump_json() + "\n", encoding="utf-8")
    mprograms = MicroProgramDirectory(
        term_key=term,
        programs=[MicroProgram(code="H01", name=mprogram_name, rules_text="至少 9 學分")],
    )
    (d / "mprograms.json").write_text(mprograms.model_dump_json(), encoding="utf-8")
    return d


# ── 乾淨：只含已知碼位 / 例外 ──

def test_clean_when_only_known_and_exception(tmp_path):
    # 已考證造字 E1B3（在 PUA_MAP）+ 壞損孤例 EF0D（例外）→ 皆不算新
    _write_term(tmp_path, name_zh=f"測試課程 林{E1B3}", notes=f"造字 {EF0D} 保留")
    assert scan_canonical(tmp_path, ["115-1"]) == []


def test_clean_prints_and_zero_exit(tmp_path, capsys):
    _write_term(tmp_path, name_zh=f"林{E1B3}")
    rc = cli.main(["pua-scan", "--terms", "115-1", "--out", str(tmp_path)])
    assert rc == 0
    assert "pua-scan clean" in capsys.readouterr().out


def test_ef0d_alone_is_not_new(tmp_path):
    _write_term(tmp_path, notes=f"孤例 {EF0D}")
    assert scan_canonical(tmp_path, ["115-1"]) == []
    assert 0xEF0D in KNOWN_EXCEPTIONS


# ── 未考證新碼位 → 命中 ──

def test_flags_unknown_codepoint(tmp_path):
    _write_term(tmp_path, notes=f"某{E2FE}師")
    hits = scan_canonical(tmp_path, ["115-1"])
    assert [h.codepoint for h in hits] == [0xE2FE]
    assert hits[0].context and len(hits[0].context) <= 20
    assert "notes" in hits[0].field  # 指到出現欄位


def test_unknown_nonzero_exit_and_codepoint_in_output(tmp_path, capsys):
    _write_term(tmp_path, name_zh=f"課{E2FE}名")
    rc = cli.main(["pua-scan", "--terms", "115-1", "--out", str(tmp_path)])
    assert rc == 1
    assert "E2FE" in capsys.readouterr().err.upper()


def test_flags_in_details_and_mprograms(tmp_path):
    # 三種來源檔都要掃到
    _write_term(tmp_path, assessment=f"報告{E2FE} 50%", mprogram_name=f"學程{E2FE}")
    hits = scan_canonical(tmp_path, ["115-1"])
    assert [h.codepoint for h in hits] == [0xE2FE]  # 去重：同碼位只報一次


# ── 邊界：缺檔 / 缺學期不炸 ──

def test_missing_term_dir_is_clean(tmp_path):
    assert scan_canonical(tmp_path, ["199-1"]) == []


def test_partial_files_ok(tmp_path):
    d = tmp_path / "canonical" / "115-1"
    d.mkdir(parents=True)
    # 只有 catalog.ndjson，無 details/mprograms
    course = CourseOffering(
        term_key="115-1", offering_id="300777",
        name=LocalizedText(zh=f"林{E2FE}"), selection=Selection(cwish_subj="300777"),
    )
    (d / "catalog.ndjson").write_text(course.model_dump_json() + "\n", encoding="utf-8")
    hits = scan_canonical(tmp_path, ["115-1"])
    assert [h.codepoint for h in hits] == [0xE2FE]


# ── Adobe/PDF 殘留區（F3xx-F7xx）：依 pua.py 設計「不處理、保留原樣」，
#    不該每次掃描都當成新碼位噪音，否則真正的新造字會被淹沒。

def test_adobe_pdf_residue_range_is_not_flagged_as_new(tmp_path):
    # 115-1 實際出現過的 9 個：U+F332 / F6B1-F6B5 / F6F3 / F762 / F793
    residue = "".join(chr(cp) for cp in
                      (0xF332, 0xF6B1, 0xF6B2, 0xF6B3, 0xF6B4, 0xF6B5, 0xF6F3, 0xF762, 0xF793))
    _write_term(tmp_path, notes=f"課程進度 {residue} 說明")
    assert scan_canonical(tmp_path, ["115-1"]) == [], (
        "F3xx-F7xx 是 Word/PDF 字型殘留、無可靠對照表（pua.py 檔頭第 3 條），"
        "不該報成待考證的新造字"
    )


def test_word_symbol_range_still_flagged_when_unmapped(tmp_path):
    # F0xx 是 Word 符號字型殘留、**有** Wingdings/Symbol 對照表可查 → 未收錄就該報
    unmapped_f0 = chr(0xF0AA)  # 不在 PUA_MAP 的 F0xx
    _write_term(tmp_path, notes=f"項目 {unmapped_f0} 符號")
    hits = scan_canonical(tmp_path, ["115-1"])
    assert [h.codepoint for h in hits] == [0xF0AA]


def test_school_glyph_range_still_flagged(tmp_path):
    # E 區學校造字：有 GServer 可考證 → 未收錄一定要報（這是本掃描的主要目的）
    _write_term(tmp_path, notes=f"某{E2FE}師")
    hits = scan_canonical(tmp_path, ["115-1"])
    assert [h.codepoint for h in hits] == [ord(E2FE)]


# ── 2026-09：51 個待辦碼位清空後的迴歸鎖定 ──
#    目的是「有命中＝真的有待辦」；這批全部靜音，但相鄰的未知碼位仍須報出來。

def test_2026_09_resolved_codepoints_are_all_silent(tmp_path):
    # 23 個學校造字進 PUA_MAP、22 個 Wingdings 進 PUA_MAP、
    # 4 個 E 區子集殘留進 KNOWN_EXCEPTIONS、F81A/F845 併入 _RESIDUE_RANGES
    resolved = (0xE005, 0xE202, 0xF081, 0xF08A, 0xF026,        # 已收錄
                0xE922, 0xE9AF, 0xEEE8, 0xEF0F,                # 例外
                0xF81A, 0xF845)                                # 殘留區
    _write_term(tmp_path, notes="".join(chr(cp) for cp in resolved))
    assert scan_canonical(tmp_path, ["115-1"]) == [], (
        "2026-09 已逐碼考證完畢的 51 個碼位不該再報成待辦"
    )


def test_subset_residue_upper_bound_still_reports_beyond_bmp_pua(tmp_path):
    # 殘留區上界收在 F8FF（BMP PUA 結尾）；未落在任何已知區間的碼位仍要報
    _write_term(tmp_path, notes=f"{chr(0xE300)} 與 {chr(0xF100)}")
    hits = scan_canonical(tmp_path, ["115-1"])
    assert [h.codepoint for h in hits] == [0xE300, 0xF100], (
        "E300（學校造字區之外的 E 區）與 F100（殘留區之外的 F 區）都不在已知範圍，須報出"
    )
