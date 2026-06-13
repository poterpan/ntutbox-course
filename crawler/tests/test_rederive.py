"""離線 re-derive 測試：把『壞掉的』內嵌班級（kind=regular/unit=None）修回 directory 真相。"""
import json
from pathlib import Path

from models import ClassDirectory, ClassKind, ClassRef, EnrollmentLatest, TermCatalog, TermInfo
from ntut_catalog.rederive import rederive_term


def _write_buggy_term(term_dir: Path):
    term_dir.mkdir(parents=True, exist_ok=True)
    # directory：真相——9001 是 pool（unit=14）、3032 是 regular 二年級（unit=59）
    directory = ClassDirectory(term_key="114-1", classes=[
        ClassRef(code="3032", name="資工二", kind=ClassKind.regular, unit_code="59", grade=2),
        ClassRef(code="9001", name="博雅課程(三)", kind=ClassKind.pool, unit_code="14", grade=None),
    ])
    (term_dir / "classes.json").write_text(directory.model_dump_json(), encoding="utf-8")

    # catalog：內嵌班級全是『壞的』預設（kind=regular、unit/grade 空）
    catalog = TermCatalog(
        term=TermInfo(key="114-1", year=114, semester=1),
        courses=[],
    )
    raw = json.loads(catalog.model_dump_json())
    raw["courses"] = [{
        "term_key": "114-1", "offering_id": "300001",
        "name": {"zh": "博雅課"},
        "classes": [{"code": "9001", "name": "博雅課程(三)", "kind": "regular",
                     "unit_code": None, "grade": None}],
        "selection": {"cwish_subj": "300001", "candidate_cunums": ["9001"]},
    }]
    (term_dir / "catalog.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


def test_rederive_fixes_embedded_pool(tmp_path):
    term_dir = tmp_path / "v1" / "terms" / "114-1"
    _write_buggy_term(term_dir)

    stats = rederive_term(term_dir)
    assert stats == {"term": "114-1", "courses": 1, "patched": 1, "fallback": 0}

    cat = TermCatalog.model_validate_json((term_dir / "catalog.json").read_text(encoding="utf-8"))
    cl = cat.courses[0].classes[0]
    assert cl.kind == ClassKind.pool          # 從 regular 修回 pool
    assert cl.unit_code == "14"               # 從 None 補上
    assert cl.grade is None


def test_rederive_idempotent(tmp_path):
    term_dir = tmp_path / "v1" / "terms" / "114-1"
    _write_buggy_term(term_dir)
    rederive_term(term_dir)
    second = rederive_term(term_dir)
    assert second["patched"] == 0             # 第二次無變更
