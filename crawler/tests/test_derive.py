"""derive 層：canonical → v1 的確定性與全量重建（spec §1 derive 規則、§6 manifest 合約）。"""
import datetime as dt
import json
from pathlib import Path

import pytest
from freezegun import freeze_time

from models import CourseDetail, LocalizedText, Manifest, Syllabus
from tests._fakes import record_enrollment
from ntut_catalog.artifacts import (
    derive,
    write_calendar_events,
    write_canonical,
    write_term_calendar,
)
from ntut_catalog.calendar_events import parse_calendar_events
from ntut_catalog.detail import write_details
from ntut_catalog.term_calendar import build_all_term_calendars

REPO = Path(__file__).resolve().parents[2]
SNAPSHOT_ICS = (REPO / "docs" / "research" / "assets" / "2026-09-16-calendar-ics-evaluation"
                / "raw" / "gcal-basic.ics")


@pytest.fixture
def canonical(tmp_path, sample_result):
    """一份涵蓋各種產物的 canonical：catalog/classes/enrollment/details/mprograms/standards/行事曆。"""
    out = tmp_path / "data"
    write_canonical(sample_result, out)
    record_enrollment(out, "115-1", sample_result.enrollment, "2026-09-01T00:00:00+08:00")
    term_dir = out / "canonical" / "115-1"
    oid = sample_result.catalog.courses[0].offering_id
    write_details([_detail("115-1", oid)], out)
    (term_dir / "mprograms.json").write_text('{"term_key":"115-1","programs":[]}', encoding="utf-8")
    std = out / "canonical" / "standards"
    std.mkdir(parents=True)
    (std / "115.json").write_text('{"entry_year":115}', encoding="utf-8")
    feed = parse_calendar_events(SNAPSHOT_ICS.read_text(encoding="utf-8"), today=dt.date(2026, 9, 16))
    write_calendar_events(feed, out)
    for key, cal in build_all_term_calendars(feed.events, ["115-1", "115-2"], "u", "sha").items():
        write_term_calendar(cal, key, out)
    return out


def _detail(term_key: str, oid: str, schedule: str = "第1週：課程介紹\n第2週：基礎概念"):
    return CourseDetail(term_key=term_key, offering_id=oid, name=LocalizedText(zh="測試課程"),
                        syllabi=[Syllabus(teacher_code="T0001", teacher_name="測試教師",
                                          schedule=schedule)])


def _snapshot(v1: Path) -> dict:
    return {str(p.relative_to(v1)): p.read_bytes() for p in sorted(v1.rglob("*")) if p.is_file()}


def test_derive_is_byte_identical_across_system_times(canonical):
    """同一份 canonical、兩個不同的凍結系統時間（跨學年度交界）→ v1 逐位元組相同。"""
    with freeze_time("2026-07-31T23:59:00+08:00"):
        derive(canonical)
    first = _snapshot(canonical / "v1")
    with freeze_time("2031-02-14T09:30:00+08:00"):
        derive(canonical)
    second = _snapshot(canonical / "v1")
    assert first.keys() == second.keys()
    assert first == second
    # 各類產物都有涵蓋到（不然這條測試等於只驗了 manifest）
    assert {"manifest.json", "terms/115-1/catalog.json", "terms/115-1/enrollment.json",
            "terms/115-1/calendar.json", "terms/115-2/calendar.json", "calendar/events.json",
            "standards/115.json", "terms/115-1/mprograms.json"} <= set(first)
    assert any(k.startswith("terms/115-1/course/") for k in first)


def test_derived_manifest_has_no_timestamps_and_carries_catalog_count(canonical, sample_result):
    manifest = derive(canonical)
    raw = json.loads((canonical / "v1" / "manifest.json").read_text(encoding="utf-8"))
    assert raw["generated_at"] is None and raw["published_at"] is None   # publish 才寫
    assert manifest.terms["115-1"].catalog.count == len(sample_result.catalog.courses)
    assert raw["terms"]["115-1"]["catalog"]["count"] == len(sample_result.catalog.courses)
    assert sorted(manifest.calendars) == ["115-1", "115-2"]
    Manifest.model_validate(raw)


def test_derive_starts_from_an_empty_v1(canonical):
    """殘留在 v1/ 的舊產物會讓 publish 永遠把它當成「本地還有」而刪不掉 R2 上的過期檔。"""
    stale = canonical / "v1" / "terms" / "115-1" / "course" / "999999.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}", encoding="utf-8")
    derive(canonical)
    assert not stale.exists()
    assert (canonical / "v1" / "manifest.json").exists()


def test_cli_derive_subcommand(canonical, capsys):
    from ntut_catalog import cli
    assert cli.main(["derive", "--out", str(canonical)]) == 0
    assert (canonical / "v1" / "manifest.json").exists()
    assert "derive done" in capsys.readouterr().out


def test_fetch_commands_no_longer_write_v1():
    """spec §1：fetch 層只寫 canonical。9 處 build_v1 呼叫已移除，CLI 不可再引用它。"""
    import inspect
    from ntut_catalog import cli
    assert "build_v1(" not in inspect.getsource(cli)


# ------------------------------------------------------------ 逐週進度移到 derive（spec §4）

def test_derive_computes_weekly_progress_without_timestamps(canonical, sample_result):
    derive(canonical)
    oid = sample_result.catalog.courses[0].offering_id
    course = json.loads((canonical / "v1" / "terms" / "115-1" / "course" / f"{oid}.json")
                        .read_text(encoding="utf-8"))
    assert "generated_at" not in course
    wp = course["syllabi"][0]["weekly_progress"]
    assert wp["status"] in {"resolved", "partial"} and wp["weeks"][0]["topics"] == ["課程介紹"]
    assert "parsed_at" not in wp
    assert course["syllabi"][0]["schedule"].startswith("第1週")     # 原文仍在
    # canonical 仍只有原文（derive 不回寫 details.ndjson）
    raw = json.loads((canonical / "canonical" / "115-1" / "details.ndjson").read_text(encoding="utf-8"))
    assert "weekly_progress" not in raw["syllabi"][0]


def test_derive_writes_progress_report_without_generated_at(canonical):
    derive(canonical)
    path = canonical / "canonical" / "reports" / "115-1" / "weekly-progress.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    assert "generated_at" not in report
    assert report["parser_version"] and report["syllabi"] == 1
    assert report["term_weeks_available"] is True                    # 115-1 有 calendar.json
    first = path.read_bytes()
    derive(canonical)
    assert path.read_bytes() == first                                # 數字不變就沒有 diff


def test_term_without_calendar_uses_marker_path(canonical, sample_result):
    """Review Focus 4：110-1～114-2 沒有 calendar.json → 走 term=None，照常產出三態結果。"""
    r = sample_result
    r.catalog.term.key, r.catalog.term.year, r.catalog.term.semester = "114-1", 114, 1
    write_canonical(r, canonical)
    oid = r.catalog.courses[0].offering_id
    write_details([_detail("114-1", oid)], canonical)
    assert not (canonical / "canonical" / "114-1" / "calendar.json").exists()
    derive(canonical)
    course = json.loads((canonical / "v1" / "terms" / "114-1" / "course" / f"{oid}.json")
                        .read_text(encoding="utf-8"))
    wp = course["syllabi"][0]["weekly_progress"]
    assert wp is not None and wp["status"] == "partial" and wp["weeks"]
    report = json.loads((canonical / "canonical" / "reports" / "114-1" / "weekly-progress.json")
                        .read_text(encoding="utf-8"))
    assert report["term_weeks_available"] is False
    assert report["status_counts"]["partial"] == 1


# ------------------------------------------------------------ manifest 新鮮度（spec §6）

def test_manifest_freshness_comes_from_fetch_state(canonical):
    from ntut_catalog import fetch_state
    state = fetch_state.empty()
    fetch_state.update(state, "catalog", "115-1", "a", "2026-09-26T06:26:10+08:00")
    fetch_state.update(state, "catalog", "115-1", "a", "2026-09-27T06:20:00+08:00")  # 沒變
    fetch_state.update(state, "enrollment", "115-1", "e", "2026-09-27T06:20:00+08:00",
                       changed_at="2026-09-27T06:20:00+08:00")
    fetch_state.update(state, "enrollment", "115-1", "e", "2026-09-27T10:00:00+08:00",
                       changed_at="2026-09-27T06:20:00+08:00")
    fetch_state.update(state, "details", "115-1", "d", "2026-09-21T03:00:00+08:00")
    fetch_state.update(state, "calendar", None, "c", "2026-09-27T06:00:00+08:00")
    fetch_state.save(fetch_state.path_for(canonical / "canonical"), state)

    manifest = derive(canonical)
    t = manifest.terms["115-1"]
    assert (t.catalog.checked_at, t.catalog.changed_at) == \
        ("2026-09-27T06:20:00+08:00", "2026-09-26T06:26:10+08:00")
    assert t.classes.checked_at == t.catalog.checked_at
    assert (t.enrollment.checked_at, t.enrollment.changed_at) == \
        ("2026-09-27T10:00:00+08:00", "2026-09-27T06:20:00+08:00")
    assert t.periods.checked_at is None                               # 不是資料集產出的檔
    assert t.mprograms.checked_at is None                             # fetch-state 沒有這筆
    assert t.calendar.checked_at == "2026-09-27T06:00:00+08:00"
    assert manifest.calendars["115-2"].changed_at == "2026-09-27T06:00:00+08:00"
    assert t.details.model_dump() == {"checked_at": "2026-09-21T03:00:00+08:00",
                                      "changed_at": "2026-09-21T03:00:00+08:00", "count": 1}
    raw = json.loads((canonical / "v1" / "manifest.json").read_text(encoding="utf-8"))
    assert "url" not in raw["terms"]["115-1"]["details"]
    assert raw["schema_version"] == 3                                 # 新增欄位不升版
