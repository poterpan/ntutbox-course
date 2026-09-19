"""行事曆事件 feed（契約四）：feed 組裝、防呆、horizon 判準、canonical/v1 產物。

整合測試打的是版控裡的 2026-09-14 ics 快照與學校 API dump，離線、不碰網路。
"""
import datetime as dt
import json
from pathlib import Path

import pytest

from models import CalendarEventsFeed
from ntut_catalog.artifacts import (
    build_calendar_v1,
    read_calendar_event_count,
    write_calendar_events,
)
from ntut_catalog.calendar_events import (
    content_sha256,
    crawl_calendar_events,
    event_start_date,
    horizon_required_through,
    parse_calendar_events,
)
from ntut_catalog.ics import TAIPEI, parse_ics

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "docs" / "research" / "assets" / "2026-09-16-calendar-ics-evaluation"
SNAPSHOT = ASSETS / "raw" / "gcal-basic.ics"
SCHOOL_DUMP = ASSETS / "raw" / "cal-raw-threeyear.json"
FIXTURE = Path(__file__).parent / "fixtures" / "calendar_sample.ics"


class FakeCalendarClient:
    """回放固定 ics。比照 tests/_fakes.py 的手刻假 client 慣例，repo 不用 mock 套件。"""

    def __init__(self, text: str):
        self._text = text
        self.request_count = 0

    def fetch_ics(self, url: str) -> str:
        self.request_count += 1
        return self._text

    def close(self) -> None:
        pass


@pytest.fixture()
def sample_ics():
    return FIXTURE.read_text(encoding="utf-8")


# ----------------------------------------------------------------- feed 組裝

def test_feed_envelope_declares_calendar_schema_and_inclusive_semantics(sample_ics):
    feed = parse_calendar_events(sample_ics, today=dt.date(2026, 9, 16))
    # schema_version 刻意獨立於全域 SCHEMA_VERSION（=2），不然課程 schema 改版會讓 App 整份拒收
    assert feed.schema_version == 1
    assert feed.timezone == "Asia/Taipei"
    assert feed.range_end_semantics == "inclusive"
    assert feed.source.type == "google_calendar_ics"
    assert feed.source.parser_version.startswith("calendar-events/")


def test_content_sha256_ignores_source_ordering(sample_ics):
    head, _, rest = sample_ics.partition("BEGIN:VEVENT")
    blocks = ("BEGIN:VEVENT" + rest).split("BEGIN:VEVENT")[1:]
    shuffled = head + "".join("BEGIN:VEVENT" + b for b in reversed(blocks))
    assert content_sha256(parse_ics(shuffled)) == content_sha256(parse_ics(sample_ics))


def test_content_sha256_changes_when_an_event_changes(sample_ics):
    changed = sample_ics.replace("SUMMARY:期中考試", "SUMMARY:期中考試（延期）")
    assert content_sha256(parse_ics(changed)) != content_sha256(parse_ics(sample_ics))


def test_crawl_uses_client_and_returns_feed(sample_ics):
    client = FakeCalendarClient(sample_ics)
    feed = crawl_calendar_events(client, "https://example.test/x.ics")
    assert client.request_count == 1
    assert feed.source.url == "https://example.test/x.ics"
    assert len(feed.events) == 7


# ----------------------------------------------------------------- 防呆

def test_zero_events_aborts_rather_than_wiping_canonical():
    with pytest.raises(ValueError, match="0 筆"):
        parse_calendar_events("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")


def test_shrunken_feed_aborts(sample_ics):
    """解析得出來但明顯殘缺（低於既有 95%）→ 擋下，不讓殘缺結果覆寫既有 canonical。"""
    with pytest.raises(ValueError, match="低於既有"):
        parse_calendar_events(sample_ics, previous_count=100)


def test_slightly_smaller_feed_is_allowed(sample_ics):
    parse_calendar_events(sample_ics, previous_count=7)  # 不得拋錯


# ----------------------------------------------------------------- horizon

@pytest.mark.parametrize(
    "today,required",
    [
        ("2026-09-16", "2027-06-01"),  # 9~2 月：只要求當前學年度完整
        ("2026-12-01", "2027-06-01"),
        ("2027-02-28", "2027-06-01"),
        ("2027-03-01", "2028-06-01"),  # 3 月起：要求新學年度已到位（提醒開始）
        ("2027-08-31", "2028-06-01"),  # 8 月底仍在預期窗口內（112 學年度就是拖到 8 月）
        ("2027-09-01", "2028-06-01"),  # 9 月後回到「當前學年度」，此時已是 116 學年度
    ],
)
def test_horizon_required_through(today, required):
    assert horizon_required_through(dt.date.fromisoformat(today)) == dt.date.fromisoformat(required)


def test_horizon_ok_while_current_year_complete(sample_ics):
    # fixture 最遠 2027-04-01 → 對 2025 學年度（需涵蓋到 2026-06）綽綽有餘
    feed = parse_calendar_events(sample_ics, today=dt.date(2025, 10, 1))
    assert feed.horizon.max_start == "2027-04-01"
    assert feed.horizon.ok is True


def test_horizon_flags_insufficient_but_does_not_raise(sample_ics):
    """horizon 不足是**告警**不是失敗——feed 沒有新學年不代表現有資料壞了。"""
    feed = parse_calendar_events(sample_ics, today=dt.date(2027, 3, 1))
    assert feed.horizon.ok is False
    assert len(feed.events) == 7           # 照常產出


# ----------------------------------------------------------------- 產物

def test_write_skips_rewrite_when_content_unchanged(tmp_path, sample_ics):
    feed = parse_calendar_events(sample_ics, today=dt.date(2026, 9, 16))
    assert write_calendar_events(feed, tmp_path) is True
    assert write_calendar_events(feed, tmp_path) is False   # 每日跑但內容沒變 → 不製造噪音 commit
    assert read_calendar_event_count(tmp_path) == 7


def test_write_rewrites_when_content_changed(tmp_path, sample_ics):
    write_calendar_events(parse_calendar_events(sample_ics, today=dt.date(2026, 9, 16)), tmp_path)
    changed = sample_ics.replace("SUMMARY:期中考試", "SUMMARY:期中考試（延期）")
    assert write_calendar_events(parse_calendar_events(changed, today=dt.date(2026, 9, 16)),
                                 tmp_path) is True
    nd = (tmp_path / "canonical" / "calendar" / "events.ndjson").read_text(encoding="utf-8")
    assert "期中考試（延期）" in nd


def test_canonical_is_one_event_per_sorted_line(tmp_path, sample_ics):
    feed = parse_calendar_events(sample_ics, today=dt.date(2026, 9, 16))
    write_calendar_events(feed, tmp_path)
    lines = (tmp_path / "canonical" / "calendar" / "events.ndjson").read_text(
        encoding="utf-8").splitlines()
    assert len(lines) == 7
    starts = [json.loads(ln)["start_date"] or json.loads(ln)["start_at"][:10] for ln in lines]
    assert starts == sorted(starts)


def test_build_v1_round_trips_into_a_valid_feed(tmp_path, sample_ics):
    feed = parse_calendar_events(sample_ics, today=dt.date(2026, 9, 16))
    write_calendar_events(feed, tmp_path)
    assert build_calendar_v1(tmp_path, "2026-09-16T02:00:00+08:00") is True
    out = CalendarEventsFeed.model_validate_json(
        (tmp_path / "v1" / "calendar" / "events.json").read_text(encoding="utf-8"))
    # 刻意不帶建置時間戳——帶了檔案每天都不同，App 就永遠拿不到 304
    assert out.generated_at is None
    assert out.source.fetched_at == feed.source.fetched_at
    assert out.source.content_sha256 == feed.source.content_sha256
    assert [e.model_dump() for e in out.events] == [e.model_dump() for e in feed.events]


def test_build_v1_noops_without_canonical(tmp_path):
    assert build_calendar_v1(tmp_path, "2026-09-16T02:00:00+08:00") is False
    assert read_calendar_event_count(tmp_path) == 0


# ----------------------------------------------------------------- 整合（版控中的真實快照）

def test_real_snapshot_shape_matches_investigation():
    """對 2026-09-14 快照：661 筆、全天 538／有時刻 123、最遠 2027-07-03。
    數字出自 poterpan/NTUTBox#181 的實測，任一項變動代表來源或 parser 行為改了。"""
    feed = parse_calendar_events(SNAPSHOT.read_text(encoding="utf-8"), today=dt.date(2026, 9, 16))
    assert len(feed.events) == 661
    assert sum(e.all_day for e in feed.events) == 538
    assert sum(not e.all_day for e in feed.events) == 123
    assert feed.horizon.max_start == "2027-07-03"
    assert feed.horizon.ok is True
    # 全天事件一律 end-exclusive，轉 inclusive 後不得出現 end < start
    assert all(e.end_date >= e.start_date for e in feed.events if e.all_day)


def test_real_snapshot_agrees_with_school_api_event_for_event():
    """跨來源交叉驗證：正規化後的事件必須與學校 calModeApp.do 逐字相等。

    #181 的換源結論就是這個 97/97/0。它同時驗到 end-exclusive→inclusive 的轉換、
    全天判定與文字反跳脫——任何一項寫錯，這裡都會出現差異。
    """
    lo, hi = dt.date(2026, 8, 1), dt.date(2027, 7, 31)
    feed = parse_calendar_events(SNAPSHOT.read_text(encoding="utf-8"), today=dt.date(2026, 9, 16))
    mine = {
        (e.summary, event_start_date(e).isoformat(),
         (e.end_date or e.end_at[:10]))
        for e in feed.events if lo <= event_start_date(e) <= hi
    }
    school = set()
    for r in json.loads(SCHOOL_DUMP.read_text(encoding="utf-8")):
        if r.get("ownerId") == "holiday_system" or not r.get("calTitle"):
            continue  # 這 105 筆不是國定假日，只是週六日（#181 實測 522 個標記日零個落在平日）
        s_dt = dt.datetime.fromtimestamp(r["calStart"] / 1000, TAIPEI)
        e_dt = dt.datetime.fromtimestamp(r["calEnd"] / 1000, TAIPEI)
        if r["calEnd"] == r["calStart"]:
            end = s_dt.date()
        elif (e_dt.hour, e_dt.minute) == (0, 0):
            end = e_dt.date() - dt.timedelta(days=1)
        else:
            end = e_dt.date()
        end = max(end, s_dt.date())
        if lo <= s_dt.date() <= hi:
            school.add((r["calTitle"], s_dt.date().isoformat(), end.isoformat()))
    assert len(mine) == 97
    assert mine - school == set()
    assert school - mine == set()


# ----------------------------------------------------------------- CLI

def test_cli_crawl_calendar_writes_canonical_and_v1(tmp_path, monkeypatch):
    """走完整 CLI 路徑：抓取（假 client）→ canonical → build_v1 → v1/calendar/events.json。

    用真實快照而不是小 fixture——crawl-calendar 同時要推導週次表（契約三），
    小 fixture 沒有「開學」「期末考試」那些具名事件。
    """
    from ntut_catalog import cli

    monkeypatch.setattr(cli, "CalendarClient",
                        lambda: FakeCalendarClient(SNAPSHOT.read_text(encoding="utf-8")))
    assert cli.main(["crawl-calendar", "--out", str(tmp_path), "--terms", "115-1"]) == 0

    assert (tmp_path / "canonical" / "calendar" / "events.ndjson").exists()
    out = CalendarEventsFeed.model_validate_json(
        (tmp_path / "v1" / "calendar" / "events.json").read_text(encoding="utf-8"))
    assert len(out.events) == 661
    assert out.generated_at is None


def test_cli_fails_loudly_when_term_calendar_cannot_be_derived(tmp_path, monkeypatch, sample_ics):
    """來源缺具名事件（或措辭改了）→ 整個 crawl-calendar 失敗，不寫出半套產物。

    workflow 對這一步是 continue-on-error（不擋 catalog/enrollment 發布），
    但最後有一步會把它變成紅燈——靜默沿用舊週次表正是換源要消滅的失效模式。
    """
    from ntut_catalog import cli
    from ntut_catalog.term_calendar import CalendarDerivationError

    monkeypatch.setattr(cli, "CalendarClient", lambda: FakeCalendarClient(sample_ics))
    with pytest.raises(CalendarDerivationError):
        cli.main(["crawl-calendar", "--out", str(tmp_path), "--terms", "115-1"])
    assert not (tmp_path / "v1" / "terms" / "115-1" / "calendar.json").exists()


def test_v1_bytes_are_stable_when_content_did_not_change(tmp_path, sample_ics):
    """行事曆沒改的日子，v1 產物必須 **byte-identical** —— 否則 ETag 每天都變，
    App 每天重抓 193 KB。換源的理由之一就是 ics 自己沒有 ETag、直抓每次都是全量，
    我們轉出來的 CDN 版本要是也天天換，那就白轉了。"""
    from ntut_catalog.artifacts import build_calendar_v1, write_calendar_events
    feed = parse_calendar_events(sample_ics, today=dt.date(2026, 9, 16))
    write_calendar_events(feed, tmp_path)
    out = tmp_path / "v1" / "calendar" / "events.json"

    build_calendar_v1(tmp_path, "2026-09-16T02:00:00+08:00")
    first = out.read_bytes()
    build_calendar_v1(tmp_path, "2026-09-17T02:00:00+08:00")   # 隔天再建置一次
    assert out.read_bytes() == first


def test_app_contract_fixtures_are_valid(tmp_path):
    """App 端拿這三份做雙邊契約測試（events 切片／週次表／manifest）。"""
    from models import Manifest, TermCalendarFile
    fix = Path(__file__).parent / "fixtures" / "calendar"
    feed = CalendarEventsFeed.model_validate_json((fix / "events-sample.json").read_text(encoding="utf-8"))
    assert len(feed.events) == 4 and feed.range_end_semantics == "inclusive"
    cal = TermCalendarFile.model_validate_json((fix / "calendar-115-1.json").read_text(encoding="utf-8"))
    assert len(cal.terms["115-1"].weeks) == 18
    man = Manifest.model_validate_json((fix / "manifest.json").read_text(encoding="utf-8"))
    entry = man.terms["115-1"].calendar
    assert entry is not None and entry.url == "terms/115-1/calendar.json"
    assert entry.schema_version == cal.schema_version     # manifest 與檔案宣告一致
