"""pipeline（fetch job）＋登錄表，與 pipeline → merge → derive 端到端（spec §2、§3）。"""
import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from ntut_catalog import cli, pipeline, registry
from ntut_catalog import enrollment_store as es
from ntut_catalog import fetch_state as fs
from ntut_catalog.artifacts import derive
from ntut_catalog.ics import TAIPEI
from ntut_catalog.merge import merge_fetch_output
from ntut_catalog.registry import FetchContext
from tests._fakes import FakeClient
from tests.test_calendar_events import SNAPSHOT, FakeCalendarClient
from tests.test_programs import FakeProgClient


class DailyFakeClient(FakeClient, FakeProgClient):
    """catalog（csie fixture）＋微學程／課程標準 fixture 的組合；上游內容固定不變。"""

    def __init__(self):
        FakeClient.__init__(self)
        FakeProgClient.__init__(self)
        self.request_count = 0

    def close(self):
        pass


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _ctx(out, clock, client_factory=DailyFakeClient):
    return FetchContext(out, catalog_client_factory=client_factory,
                        calendar_client_factory=lambda: FakeCalendarClient(
                            SNAPSHOT.read_text(encoding="utf-8")),
                        now=clock)


def _run_daily(tmp_path, data, clock, name):
    """模擬 CI：fetch job 在自己的 checkout（data 的複本）跑，merge 在最新 data 上跑。"""
    checkout = tmp_path / f"checkout-{name}"
    if (data / "canonical").exists():
        shutil.copytree(data / "canonical", checkout / "canonical")
    stage = tmp_path / f"stage-{name}"
    result = pipeline.run("daily", None, ["115-1"], checkout, stage, ctx=_ctx(checkout, clock))
    report = merge_fetch_output(stage, data)
    return result, report


def _tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_daily_end_to_end_then_idempotent_rerun(tmp_path):
    data = tmp_path / "data"
    clock = Clock(dt.datetime(2026, 9, 26, 6, 26, 10, tzinfo=TAIPEI))
    result, report = _run_daily(tmp_path, data, clock, "1")
    assert result.ok, result.datasets
    assert {(e["name"], e["term"]) for e in result.datasets} == {
        ("calendar", None), ("catalog", "115-1"), ("mprograms", "115-1")}
    assert report.datasets() == ["calendar", "catalog", "mprograms"] and report.changed
    manifest = derive(data)
    t = manifest.terms["115-1"]
    assert t.catalog.checked_at == t.catalog.changed_at == "2026-09-26T06:26:10+08:00"
    assert t.enrollment.changed_at == "2026-09-26T06:26:00+08:00"   # 快照名的分鐘
    enr = json.loads((data / "v1" / "terms" / "115-1" / "enrollment.json").read_text(encoding="utf-8"))
    assert enr["observed_at"] == "2026-09-26T06:26:10+08:00"
    assert manifest.calendars and all(c.checked_at for c in manifest.calendars.values())
    v1_first = _tree(data / "v1")
    before = _tree(data / "canonical")

    # 隔天：上游完全沒變
    clock.t = dt.datetime(2026, 9, 27, 6, 31, 0, tzinfo=TAIPEI)
    result, report = _run_daily(tmp_path, data, clock, "2")
    assert result.ok and not report.changed
    after = _tree(data / "canonical")
    diff = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    assert diff == {"_meta/fetch-state.json", "115-1/enrollment/observations.ndjson"}
    obs_before = before["115-1/enrollment/observations.ndjson"].decode().splitlines()
    obs_after = after["115-1/enrollment/observations.ndjson"].decode().splitlines()
    assert obs_after[:-1] == obs_before and len(obs_after) == len(obs_before) + 1
    old_state = json.loads(before["_meta/fetch-state.json"])
    new_state = json.loads(after["_meta/fetch-state.json"])
    for ds, terms in new_state["datasets"].items():
        for key, entry in terms.items():
            prev = old_state["datasets"][ds][key]
            assert entry["changed_at"] == prev["changed_at"]          # 只有 checked_at 前進
            assert entry["content_sha256"] == prev["content_sha256"]
            assert entry["checked_at"] > prev["checked_at"]

    # v1：除了 manifest（checked_at）與 enrollment.json（observed_at）外逐位元組相同
    derive(data)
    v1_second = _tree(data / "v1")
    changed_v1 = {k for k in v1_first if v1_first[k] != v1_second.get(k)}
    assert changed_v1 == {"manifest.json", "terms/115-1/enrollment.json"}


def test_season_without_terms_exits_2(tmp_path, capsys):
    """Review Focus 5：不可默默用 current-term（12 月時可能是錯的學期）。"""
    assert cli.main(["pipeline", "--cadence", "season", "--out", str(tmp_path)]) == 2
    assert "--terms" in capsys.readouterr().err
    with pytest.raises(pipeline.UsageError):
        pipeline.run("season", None, [], tmp_path, tmp_path / "stage")


def test_one_dataset_failing_does_not_stop_others(tmp_path):
    class Broken(DailyFakeClient):
        def mprogram_list(self, year, sem):
            return "<html>改版了</html>"                      # 解析出 0 個學程 → fail loud

    clock = Clock(dt.datetime(2026, 9, 26, 6, 0, tzinfo=TAIPEI))
    stage = tmp_path / "stage"
    result = pipeline.run("daily", ["catalog", "mprograms"], ["115-1"], tmp_path, stage,
                          ctx=_ctx(tmp_path, clock, Broken))
    by_name = {e["name"]: e for e in result.datasets}
    assert by_name["catalog"]["ok"] and not by_name["mprograms"]["ok"]
    assert "ValueError" in by_name["mprograms"]["error"]
    assert not result.ok
    written = json.loads((stage / "pipeline-result.json").read_text(encoding="utf-8"))
    assert written["cadence"] == "daily" and len(written["datasets"]) == 2
    assert (stage / "canonical" / "115-1" / "catalog.ndjson").exists()
    assert not (stage / "canonical" / "115-1" / "mprograms.json").exists()


def test_current_term_failure_is_recorded_not_raised(tmp_path):
    def down():
        raise RuntimeError("aps.ntut.edu.tw unreachable")

    clock = Clock(dt.datetime(2026, 9, 26, 6, 0, tzinfo=TAIPEI))
    result = pipeline.run("daily", None, [], tmp_path, tmp_path / "stage",
                          ctx=_ctx(tmp_path, clock), current_term=down)
    by_name = {e["name"]: e for e in result.datasets}
    assert by_name["calendar"]["ok"]                            # 行事曆不依賴學校
    assert not by_name["catalog"]["ok"] and "unreachable" in by_name["catalog"]["error"]


def test_result_entry_shape(tmp_path):
    clock = Clock(dt.datetime(2026, 9, 26, 6, 0, 30, tzinfo=TAIPEI))
    result = pipeline.run("manual", ["catalog"], ["115-1"], tmp_path, tmp_path / "stage",
                          ctx=_ctx(tmp_path, clock))
    (e,) = result.datasets
    assert e == {"name": "catalog", "term": "115-1", "ok": True,
                 "checked_at": "2026-09-26T06:00:30+08:00", "error": None,
                 "files": ["115-1/catalog.ndjson", "115-1/classes.json",
                           "115-1/enrollment/2026-09-26T0600.ndjson"],
                 "enrollment": {"observed_at": "2026-09-26T06:00:30+08:00",
                                "snapshot": "2026-09-26T0600"}}
    rows = (tmp_path / "canonical" / "115-1" / "enrollment" / "2026-09-26T0600.ndjson") \
        .read_text(encoding="utf-8").splitlines()
    assert rows and all("observed_at" not in json.loads(r) for r in rows)
    # fetch job 不追加觀測紀錄（只在鎖內的 merge 做）
    assert not (tmp_path / "canonical" / "115-1" / "enrollment" / es.OBSERVATIONS).exists()


# ------------------------------------------------------------ 登錄表與學期規則

def test_registry_cadences():
    assert {d.name for d in registry.for_cadence("daily")} == {"calendar", "catalog", "mprograms"}
    assert {d.name for d in registry.for_cadence("weekly")} == {"details", "standards"}
    assert {d.name for d in registry.for_cadence("season")} == {"enrollment"}


def test_resolve_terms_rules():
    cur = lambda: "115-1"   # noqa: E731
    assert registry.resolve_terms("current", [], cur) == ["115-1"]
    assert registry.resolve_terms("current", ["114-2"], cur) == ["114-2"]
    assert registry.resolve_terms("active", [], cur, active_env="114-2:115-1") == ["114-2", "115-1"]
    assert registry.resolve_terms("active", [], cur, active_env="") == ["115-1"]
    assert registry.resolve_terms("none", ["115-1"], cur) == [None]
    assert registry.resolve_terms("calendar", ["115-1"], cur) == [None]


def test_standards_years_are_current_academic_year_and_previous_five():
    assert registry.standards_years(dt.date(2026, 9, 26)) == [110, 111, 112, 113, 114, 115]
    assert registry.standards_years(dt.date(2026, 7, 31)) == [109, 110, 111, 112, 113, 114]


def test_standards_fetch_writes_each_year(tmp_path, monkeypatch):
    from models import StandardDirectory
    from ntut_catalog import programs
    years = []
    # 真的展開 fixture 課程標準要 ~6 秒／年；這裡只驗「哪幾個入學年、寫到哪」
    monkeypatch.setattr(programs, "crawl_standards",
                        lambda client, y: years.append(y) or StandardDirectory(entry_year=y))
    clock = Clock(dt.datetime(2026, 9, 26, 6, 0, tzinfo=TAIPEI))
    result = pipeline.run("weekly", ["standards"], [], tmp_path, tmp_path / "stage",
                          ctx=_ctx(tmp_path, clock))
    (e,) = result.datasets
    assert e["ok"] and e["term"] is None
    assert e["files"] == [f"standards/{y}.json" for y in range(110, 116)]
    assert years == list(range(110, 116))
    assert (tmp_path / "canonical" / "standards" / "115.json").exists()


def test_writes_patterns_do_not_cross_directories():
    assert registry.matches("115-1/calendar.json", registry.expand("{term}/calendar.json", None))
    assert not registry.matches("reports/115-1/calendar.json",
                                registry.expand("{term}/calendar.json", None))
    assert registry.matches_any("115-1/enrollment/2026-09-26T0600.ndjson",
                                registry.DATASETS["catalog"].writes, "115-1")
    assert not registry.matches_any("115-2/catalog.ndjson", registry.DATASETS["catalog"].writes, "115-1")


@pytest.mark.parametrize("rel, ok", [
    ("115-1/catalog.ndjson", True), ("115-1/enrollment/2026-09-26T0610.ndjson", True),
    ("115-1/enrollment/observations.ndjson", True), ("115-1/details.ndjson", True),
    ("calendar/meta.json", True), ("115-2/calendar.json", True), ("standards/115.json", True),
    ("_meta/fetch-state.json", True), ("reports/115-1/weekly-progress.json", True),
    ("pipeline-log-x.txt", False), ("115-1/stray.json", False), ("reports/115-1/calendar.json", False),
])
def test_committable_scope_comes_from_registry(rel, ok):
    from ntut_catalog.registry import committable
    assert committable(rel) is ok
