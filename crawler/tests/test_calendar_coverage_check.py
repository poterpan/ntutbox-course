"""已發布週次表的涵蓋檢查。盯的是產物，不是來源——與 horizon 的分工見該檔 docstring。"""
import datetime as dt
import json

from infra.calendar_coverage_check import published_terms, run, term_covering

D = dt.date.fromisoformat


def _publish(tmp_path, term_key, first_week="2026-09-06", weeks=18):
    d = tmp_path / "v1" / "terms" / term_key
    d.mkdir(parents=True, exist_ok=True)
    start = D(first_week)
    payload = {"terms": {term_key: {"weeks": [
        {"number": i + 1,
         "start": (start + dt.timedelta(days=7 * i)).isoformat(),
         "end": (start + dt.timedelta(days=7 * i + 6)).isoformat()}
        for i in range(weeks)]}}}
    (d / "calendar.json").write_text(json.dumps(payload), encoding="utf-8")


def test_lists_published_terms(tmp_path):
    _publish(tmp_path, "115-1")
    _publish(tmp_path, "115-2", first_week="2027-02-21")
    assert published_terms(tmp_path) == ["115-1", "115-2"]


def test_no_terms_published(tmp_path):
    assert published_terms(tmp_path) == []
    assert run(tmp_path, today=D("2026-09-19")) == 0      # 只告警、不阻斷


def test_finds_the_term_covering_today(tmp_path):
    _publish(tmp_path, "115-1")
    _publish(tmp_path, "115-2", first_week="2027-02-21")
    assert term_covering(tmp_path, D("2026-09-19")) == "115-1"
    assert term_covering(tmp_path, D("2027-03-01")) == "115-2"


def test_gap_between_terms_has_no_covering_calendar(tmp_path):
    """學期之間的空窗期沒有對應週次表——正常，但要說出來。"""
    _publish(tmp_path, "115-1")
    assert term_covering(tmp_path, D("2027-01-20")) is None


def test_warns_when_an_expected_term_is_missing(tmp_path, capsys):
    """這正是 App 端 2026-09-19 踩到的：來源 horizon ok，但 115-2 沒上線。"""
    _publish(tmp_path, "115-1")
    run(tmp_path, today=D("2026-09-19"))
    out = capsys.readouterr().out
    assert "::warning title=週次表缺學期::" in out and "115-2" in out


def test_quiet_when_everything_is_covered(tmp_path, capsys):
    _publish(tmp_path, "115-1")
    _publish(tmp_path, "115-2", first_week="2027-02-21")
    run(tmp_path, today=D("2026-09-19"))
    assert "::warning" not in capsys.readouterr().out


def test_always_exits_zero(tmp_path):
    """8 月新學年度尚未匯入時缺學期是常態，擋住發佈只會把事件 feed 一起停掉。"""
    assert run(tmp_path, today=D("2027-08-01")) == 0
