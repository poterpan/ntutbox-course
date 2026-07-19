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
