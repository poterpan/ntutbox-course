"""infra/verify_migration.py：只允許 spec §6 欄位差異，weekly_progress 差異列報不擋。"""
import json

import pytest

from infra.verify_migration import main, render, verify


def _w(root, rel, obj):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False),
                 encoding="utf-8")


def _course(wp=None, generated_at=None, teacher="測試教師"):
    syl = {"teacher_code": "T0001", "teacher_name": teacher, "schedule": "第1週"}
    if wp is not None:
        syl["weekly_progress"] = wp
    d = {"term_key": "115-1", "offering_id": "300001", "syllabi": [syl]}
    if generated_at:
        d["generated_at"] = generated_at
    return d


def _wp(status, parsed_at=None):
    w = {"status": status, "weeks": [], "notes": [], "parser_version": "progress/1.0.0",
         "source_schedule_sha256": "x"}
    if parsed_at:
        w["parsed_at"] = parsed_at
    return w


def _manifest(new=False, enrollment_sha="e1"):
    cat = {"url": "terms/115-1/catalog.json", "sha256": "c1", "size": 10, "count": 2}
    enr = {"url": "terms/115-1/enrollment.json", "sha256": enrollment_sha, "size": 5}
    term = {"catalog": cat, "enrollment": enr, "dataset_version": "c1"}
    m = {"schema_version": 3, "generated_at": None, "published_at": None, "terms": {"115-1": term},
         "calendars": {}}
    if new:
        for e in (cat, enr):
            e.update(checked_at="2026-09-26T06:00:00+08:00", changed_at="2026-09-20T06:00:00+08:00")
        term["details"] = {"checked_at": None, "changed_at": None, "count": 1}
    return m


@pytest.fixture
def trees(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    for root, is_new in ((old, False), (new, True)):
        _w(root, "terms/115-1/catalog.json", '{"courses":[1,2]}')
        _w(root, "manifest.json", _manifest(new=is_new))
    _w(old, "terms/115-1/enrollment.json", '{"counts":{"b":1,"a":2}}')
    _w(new, "terms/115-1/enrollment.json", '{"counts":{"a":2,"b":1}}')
    _w(old, "terms/115-1/course/300001.json",
       _course(_wp("partial", "2026-09-01T00:00:00+08:00"), generated_at="2026-09-01T00:00:00+08:00"))
    _w(new, "terms/115-1/course/300001.json", _course(_wp("resolved")))
    _w(old, "terms/110-1/course/280001.json", _course())                  # 舊 canonical 沒存 progress
    _w(new, "terms/110-1/course/280001.json", _course(_wp("unparsed")))
    return old, new


def test_allowed_differences_pass_and_progress_is_reported(trees):
    old, new = trees
    r = verify(old, new)
    assert r["ok"], r["disallowed"]
    assert r["per_type"]["course/{id}.json"]["允許的變動"] == 2
    assert r["wp_before"]["115-1"]["partial"] == 1 and r["wp_after"]["115-1"]["resolved"] == 1
    assert r["wp_before"]["110-1"]["（無）"] == 1 and r["wp_after"]["110-1"]["unparsed"] == 1
    assert r["per_type"]["enrollment.json"]["允許的變動（僅鍵順序）"] == 1
    text = render(r, old, new)
    assert "**通過**" in text and "| 110-1 | 0 / 0 / 0 / 1 | 0 / 0 / 1 / 0 | 1 |" in text


def test_manifest_sha_change_allowed_only_for_loosely_equal_files(trees):
    old, new = trees
    _w(new, "manifest.json", _manifest(new=True, enrollment_sha="e2"))
    assert verify(old, new)["ok"]                      # enrollment.json 只差鍵順序 → sha 可變
    _w(new, "terms/115-1/enrollment.json", '{"counts":{"a":3,"b":1}}')
    r = verify(old, new)
    assert not r["ok"]
    assert any("enrollment.json" in d and "$.counts.a" in d for d in r["disallowed"])


@pytest.mark.parametrize("mutate, needle", [
    (lambda new: _w(new, "terms/115-1/catalog.json", '{"courses":[1]}'), "catalog.json"),
    (lambda new: _w(new, "terms/115-1/extra.json", "{}"), "舊版沒有這個檔"),
    (lambda new: _w(new, "terms/115-1/course/300001.json", _course(_wp("resolved", "x"))),
     "parsed_at"),
    (lambda new: _w(new, "terms/115-1/course/300001.json", _course(_wp("resolved"), teacher="別人")),
     "teacher_name"),
    (lambda new: _w(new, "manifest.json", dict(_manifest(new=True), min_app_version="9.9")),
     "min_app_version"),
])
def test_disallowed_differences_fail(trees, mutate, needle):
    old, new = trees
    mutate(new)
    r = verify(old, new)
    assert not r["ok"]
    assert any(needle in d for d in r["disallowed"]), r["disallowed"]


def test_cli_exit_codes_and_report(trees, tmp_path):
    old, new = trees
    report = tmp_path / "r.md"
    assert main([str(old), str(new), "--report", str(report)]) == 0
    assert report.read_text(encoding="utf-8").startswith("# 管線 v2 遷移驗證報告")
    _w(new, "terms/115-1/catalog.json", "{}")
    assert main([str(old), str(new)]) == 1
