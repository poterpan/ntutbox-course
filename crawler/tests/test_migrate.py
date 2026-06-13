"""遷移既有（內嵌 enrollment）資料 → 新 canonical（structural + snapshot）。"""
import json

from models import (
    ClassDirectory,
    ClassRef,
    CourseOffering,
    Enrollment,
    EnrollmentLatest,
    LocalizedText,
    Selection,
    TermCatalog,
)
from ntut_catalog.migrate import migrate_all


def _write_old_term(root, term="115-1"):
    """造舊格式：canonical/{term}/catalog.ndjson（內嵌 enrollment）+ v1/.../classes.json。"""
    canon = root / "canonical" / term
    canon.mkdir(parents=True, exist_ok=True)
    course = CourseOffering(
        term_key=term,
        offering_id="300001",
        name=LocalizedText(zh="測試課"),
        selection=Selection(cwish_subj="300001", candidate_cunums=["2646"]),
        classes=[ClassRef(code="2646", name="博雅課程(一)")],
        enrollment=Enrollment(
            enrolled_count=73, withdrawn_count=2, observed_at="2026-06-13T04:00:00+08:00"
        ),
        raw_fields={"enrolled": "73", "withdrawn": "2"},
    )
    (canon / "catalog.ndjson").write_text(
        course.model_dump_json(exclude_none=False) + "\n", encoding="utf-8"
    )
    v1 = root / "v1" / "terms" / term
    v1.mkdir(parents=True, exist_ok=True)
    (v1 / "classes.json").write_text(
        ClassDirectory(term_key=term, classes=[ClassRef(code="2646", name="博雅課程(一)")]).model_dump_json(),
        encoding="utf-8",
    )


def test_migrate_strips_volatile_and_seeds_snapshot(tmp_path):
    _write_old_term(tmp_path)
    migrate_all(tmp_path, "2026-06-13T05:00:00+08:00")

    nd = (tmp_path / "canonical" / "115-1" / "catalog.ndjson").read_text(encoding="utf-8").splitlines()
    course = json.loads(nd[0])
    assert course["enrollment"]["enrolled_count"] is None     # 結構化
    assert "enrolled" not in course["raw_fields"]

    # snapshot 日期取 observed_at 的日期（2026-06-13）
    snap = tmp_path / "canonical" / "115-1" / "enrollment" / "2026-06-13.ndjson"
    rec = json.loads(snap.read_text(encoding="utf-8").splitlines()[0])
    assert rec == {"offering_id": "300001", "enrolled_count": 73,
                   "withdrawn_count": 2, "observed_at": "2026-06-13T04:00:00+08:00"}

    # classes 落到 canonical
    assert (tmp_path / "canonical" / "115-1" / "classes.json").exists()

    # build_v1 還原 enrollment
    enr = EnrollmentLatest.model_validate_json(
        (tmp_path / "v1" / "terms" / "115-1" / "enrollment.json").read_text(encoding="utf-8")
    )
    assert enr.counts["300001"].enrolled_count == 73


def test_migrate_idempotent(tmp_path):
    _write_old_term(tmp_path)
    migrate_all(tmp_path, "2026-06-13T05:00:00+08:00")
    snap = tmp_path / "canonical" / "115-1" / "enrollment" / "2026-06-13.ndjson"
    before = snap.read_text(encoding="utf-8")
    migrate_all(tmp_path, "2026-06-13T06:00:00+08:00")  # 再跑：已結構化 → 不該用 null 覆寫 snapshot
    assert snap.read_text(encoding="utf-8") == before
