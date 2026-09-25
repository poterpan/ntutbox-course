"""enrollment_store：分鐘命名、去重、觀測紀錄、latest／history（spec §5）。"""
import json

from ntut_catalog import enrollment_store as es

A = [{"offering_id": "300001", "enrolled_count": 10, "withdrawn_count": 0},
     {"offering_id": "300002", "enrolled_count": 5, "withdrawn_count": 1}]
B = [{"offering_id": "300001", "enrolled_count": 12, "withdrawn_count": 0},
     {"offering_id": "300002", "enrolled_count": 5, "withdrawn_count": 1}]


def _files(term_dir):
    return sorted(p.name for p in (term_dir / "enrollment").iterdir())


def test_stamp_is_taipei_minute():
    assert es.stamp_of("2026-09-07T10:00:59+08:00") == "2026-09-07T1000"
    assert es.stamp_of("2026-09-07T02:05:00+00:00") == "2026-09-07T1005"   # 換成台北時間
    assert es.stamp_to_iso("2026-09-07T1005") == "2026-09-07T10:05:00+08:00"


def test_candidate_rows_have_no_timestamp(tmp_path):
    path = es.write_candidate(tmp_path, A, "2026-09-07T10:00:12+08:00")
    assert path.name == "2026-09-07T1000.ndjson"
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert rows == A and all("observed_at" not in r for r in rows)


def test_identical_content_is_not_written_again(tmp_path):
    assert es.write_snapshot(tmp_path, A, "2026-09-07T10:00:00+08:00") == ("2026-09-07T1000", True)
    assert es.write_snapshot(tmp_path, A, "2026-09-07T11:00:00+08:00") == ("2026-09-07T1000", False)
    assert es.write_snapshot(tmp_path, B, "2026-09-07T12:00:00+08:00") == ("2026-09-07T1200", True)
    assert _files(tmp_path) == ["2026-09-07T1000.ndjson", "2026-09-07T1200.ndjson"]


def test_dedupe_compares_time_neighbours_not_just_the_last(tmp_path):
    """過期 checkout 晚進鎖：較早的觀測與「之後那份」相同 → 不插一份重複快照。"""
    es.write_snapshot(tmp_path, A, "2026-09-07T09:00:00+08:00")
    es.write_snapshot(tmp_path, B, "2026-09-07T10:00:00+08:00")
    # 09:58 觀測到 B（與 10:00 那份相同）但較晚合併
    assert es.write_snapshot(tmp_path, B, "2026-09-07T09:58:00+08:00") == ("2026-09-07T1000", False)
    # 09:30 觀測到 A（與 09:00 相同）
    assert es.write_snapshot(tmp_path, A, "2026-09-07T09:30:00+08:00") == ("2026-09-07T0900", False)
    assert len(_files(tmp_path)) == 2


def test_same_minute_different_content_takes_next_free_minute(tmp_path):
    es.write_snapshot(tmp_path, A, "2026-09-07T10:00:05+08:00")
    assert es.write_snapshot(tmp_path, B, "2026-09-07T10:00:40+08:00") == ("2026-09-07T1001", True)


def test_latest_and_history_follow_observation_time(tmp_path):
    for t, rows in [("2026-09-07T10:00:00+08:00", A), ("2026-09-07T11:00:00+08:00", A),
                    # 12:00、13:00 沒爬到（斷點）
                    ("2026-09-07T14:00:00+08:00", B)]:
        name, _ = es.write_snapshot(tmp_path, rows, t)
        es.append_observation(tmp_path, t, name)
    # 追加順序不等於時間序：一筆較早的觀測最後才合併進來
    es.append_observation(tmp_path, "2026-09-07T09:00:00+08:00", "2026-09-07T1000")

    rows, observed = es.latest(tmp_path)
    assert rows == B and observed == "2026-09-07T14:00:00+08:00"
    hist = list(es.history(tmp_path))
    assert [t for t, _ in hist] == ["2026-09-07T09:00:00+08:00", "2026-09-07T10:00:00+08:00",
                                    "2026-09-07T11:00:00+08:00", "2026-09-07T14:00:00+08:00"]
    assert [r for _, r in hist] == [A, A, A, B]            # 沒變的觀測延用同一份快照
    assert _files(tmp_path) == ["2026-09-07T1000.ndjson", "2026-09-07T1400.ndjson",
                                "observations.ndjson"]


def test_latest_without_observations(tmp_path):
    assert es.latest(tmp_path) == ([], None)
    es.write_snapshot(tmp_path, A, "2026-09-07T10:00:00+08:00")
    assert es.latest(tmp_path) == (A, None)                # 尚未遷移的舊資料：有數字、無時間


def test_legacy_names_are_not_treated_as_snapshots(tmp_path):
    d = tmp_path / "enrollment"
    d.mkdir()
    (d / "2026-09-01.ndjson").write_text("{}\n", encoding="utf-8")
    (d / "2026-09-01T10.ndjson").write_text("{}\n", encoding="utf-8")
    assert es.snapshots(tmp_path) == []
