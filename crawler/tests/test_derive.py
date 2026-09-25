"""derive 層：canonical → v1 的確定性與全量重建（spec §1 derive 規則、§6 manifest 合約）。"""
import datetime as dt
import json
from pathlib import Path

import pytest
from freezegun import freeze_time

from models import Manifest
from ntut_catalog.artifacts import (
    derive,
    write_calendar_events,
    write_canonical,
    write_enrollment_snapshot,
    write_term_calendar,
)
from ntut_catalog.calendar_events import parse_calendar_events
from ntut_catalog.term_calendar import build_all_term_calendars

REPO = Path(__file__).resolve().parents[2]
SNAPSHOT_ICS = (REPO / "docs" / "research" / "assets" / "2026-09-16-calendar-ics-evaluation"
                / "raw" / "gcal-basic.ics")


@pytest.fixture
def canonical(tmp_path, sample_result):
    """一份涵蓋各種產物的 canonical：catalog/classes/enrollment/details/mprograms/standards/行事曆。"""
    out = tmp_path / "data"
    write_canonical(sample_result, out)
    write_enrollment_snapshot("115-1", sample_result.enrollment, out, "2026-09-01")
    term_dir = out / "canonical" / "115-1"
    oid = sample_result.catalog.courses[0].offering_id
    (term_dir / "details.ndjson").write_text(
        json.dumps({"offering_id": oid, "syllabi": []}) + "\n", encoding="utf-8")
    (term_dir / "mprograms.json").write_text('{"term_key":"115-1","programs":[]}', encoding="utf-8")
    std = out / "canonical" / "standards"
    std.mkdir(parents=True)
    (std / "115.json").write_text('{"entry_year":115}', encoding="utf-8")
    feed = parse_calendar_events(SNAPSHOT_ICS.read_text(encoding="utf-8"), today=dt.date(2026, 9, 16))
    write_calendar_events(feed, out)
    for key, cal in build_all_term_calendars(feed.events, ["115-1", "115-2"], "u", "sha").items():
        write_term_calendar(cal, key, out)
    return out


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
