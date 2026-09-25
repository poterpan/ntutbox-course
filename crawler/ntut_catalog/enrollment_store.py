"""enrollment 時序的讀寫介面（spec §5）。derive 與日後功能只經這裡讀寫；換儲存只改這支。

佈局（data branch，`canonical/{term}/enrollment/`）：
  {YYYY-MM-DDTHHMM}.ndjson   快照：一行一課 `{offering_id, enrolled_count, withdrawn_count}`，
                             檔名＝台北時間精確到分，**列內不帶時間戳**；內容與相鄰快照相同就不寫。
                             永不改寫、永不刪除。
  observations.ndjson        觀測紀錄：每次成功爬取追加一行
                             `{"observed_at": "…+08:00", "snapshot": "2026-09-07T1000"}`。

為什麼要把「觀測」與「快照」拆開：人數多半整天不動，每次都存一份快照只是重複；
但只存有變的快照又分不出「確認過、數字沒變」與「那段時間根本沒爬到」。
觀測紀錄補上後者——圖表可重取樣到任意固定間隔（沒變 → 延用前值；無紀錄 → 斷線）。

寫入分兩段（spec §3）：
  - fetch job（不上鎖、checkout 可能過期）只用 `write_candidate` 寫一份**候選**快照，
    不判斷有沒有變；
  - commit-publish job（上鎖、對最新 data branch）才用 `write_snapshot` 去重、
    `append_observation` 追加觀測。daily 與 season 會同時寫同一學期，去重必須在鎖內做。
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from ntut_catalog.ics import TAIPEI

OBSERVATIONS = "observations.ndjson"
_STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{4}$")
_STAMP_FMT = "%Y-%m-%dT%H%M"


def stamp_of(observed_at: str) -> str:
    """ISO 8601 觀測時間 → 快照檔名主幹 `YYYY-MM-DDTHHMM`（一律換成台北時間）。"""
    return dt.datetime.fromisoformat(observed_at).astimezone(TAIPEI).strftime(_STAMP_FMT)


def stamp_to_iso(stamp: str) -> str:
    """快照檔名主幹 → ISO 8601（+08:00，秒數為 0）。fetch-state 的 enrollment `changed_at` 用。"""
    return (dt.datetime.strptime(stamp, _STAMP_FMT).replace(tzinfo=TAIPEI)
            .isoformat(timespec="seconds"))


def rows_from_enrollment(enrollment) -> List[dict]:
    """EnrollmentLatest → 快照列（依課號排序；不帶 observed_at）。

    排序讓「內容相同」與「位元組相同」等價——去重直接比文字即可。
    """
    return [
        {"offering_id": oid, "enrolled_count": e.enrolled_count,
         "withdrawn_count": e.withdrawn_count}
        for oid, e in sorted(enrollment.counts.items())
    ]


def _dump_rows(rows: List[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def _read_rows(path: Path) -> List[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def snapshots(term_dir: Path) -> List[str]:
    """既有快照的檔名主幹（時間序＝字典序）。只認 `YYYY-MM-DDTHHMM`。"""
    d = term_dir / "enrollment"
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.ndjson") if _STAMP_RE.match(p.stem))


def write_candidate(term_dir: Path, rows: List[dict], observed_at: str) -> Path:
    """fetch job：無條件寫一份候選快照（去重交給上鎖的 merge）。回傳路徑。"""
    d = term_dir / "enrollment"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{stamp_of(observed_at)}.ndjson"
    path.write_text(_dump_rows(rows), encoding="utf-8")
    return path


def write_snapshot(term_dir: Path, rows: List[dict], observed_at: str) -> Tuple[str, bool]:
    """merge（鎖內、最新 HEAD）：寫入快照並去重。回傳 (觀測該指向的快照名, 是否新寫了檔)。

    去重比的是**時間上相鄰**的快照（檔名 ≤ 本次者的最後一份、以及之後的第一份），不是
    「字典序最後一份」：daily 與 season 以過期 checkout 先後進鎖時，較早觀測的那份可能
    較晚才合併進來；只比最後一份會在序列中間插進一份與前一份相同的重複快照。
    與任一相鄰者內容相同 → 不寫，觀測直接指向它。

    檔名衝突（同一分鐘另一份不同內容，極少見）→ 往後找下一個空的分鐘，快照名只是 id，
    真正的觀測時間在 observations.ndjson。
    """
    text = _dump_rows(rows)
    d = term_dir / "enrollment"
    d.mkdir(parents=True, exist_ok=True)
    stamp = stamp_of(observed_at)
    existing = snapshots(term_dir)
    before = [s for s in existing if s <= stamp]
    after = [s for s in existing if s > stamp]
    for neighbour in ([before[-1]] if before else []) + ([after[0]] if after else []):
        if (d / f"{neighbour}.ndjson").read_text(encoding="utf-8") == text:
            return neighbour, False
    t = dt.datetime.strptime(stamp, _STAMP_FMT)
    while (d / f"{t.strftime(_STAMP_FMT)}.ndjson").exists():
        t += dt.timedelta(minutes=1)
    name = t.strftime(_STAMP_FMT)
    (d / f"{name}.ndjson").write_text(text, encoding="utf-8")
    return name, True


def append_observation(term_dir: Path, observed_at: str, snapshot: str) -> None:
    """追加一行觀測紀錄。**只由 merge 呼叫**（append_only 檔，spec §3）。"""
    d = term_dir / "enrollment"
    d.mkdir(parents=True, exist_ok=True)
    with (d / OBSERVATIONS).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"observed_at": observed_at, "snapshot": snapshot},
                           ensure_ascii=False) + "\n")


def observations(term_dir: Path) -> List[Dict[str, str]]:
    """全部觀測紀錄，依 observed_at 排序（檔內是合併順序，不保證時間序）。"""
    p = term_dir / "enrollment" / OBSERVATIONS
    if not p.exists():
        return []
    rows = _read_rows(p)
    return sorted(rows, key=lambda r: dt.datetime.fromisoformat(r["observed_at"]))


def latest(term_dir: Path) -> Tuple[List[dict], Optional[str]]:
    """最後一次觀測的 (快照列, observed_at)。

    以**觀測時間**為準而不是檔名：過期 checkout 晚進鎖時，最後追加的那行不一定最新。
    沒有觀測紀錄（尚未遷移的舊資料）→ 退回字典序最後一份快照、observed_at 為 None。
    """
    obs = observations(term_dir)
    if obs:
        last = obs[-1]
        return _read_rows(term_dir / "enrollment" / f"{last['snapshot']}.ndjson"), last["observed_at"]
    snaps = snapshots(term_dir)
    if not snaps:
        return [], None
    return _read_rows(term_dir / "enrollment" / f"{snaps[-1]}.ndjson"), None


def history(term_dir: Path) -> Iterator[Tuple[str, List[dict]]]:
    """依觀測時間逐筆回傳 (observed_at, 快照列)。

    兩筆觀測之間的空檔就是「沒爬到」——這裡不補值，重取樣是消費端的事。
    同一份快照被多次觀測時各回傳一次（「確認過、數字沒變」）。
    """
    cache: Dict[str, List[dict]] = {}
    for o in observations(term_dir):
        name = o["snapshot"]
        if name not in cache:
            cache[name] = _read_rows(term_dir / "enrollment" / f"{name}.ndjson")
        yield o["observed_at"], cache[name]
