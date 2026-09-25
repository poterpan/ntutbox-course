"""commit-publish job 的合併邏輯（spec §3 job 2；在 `concurrency: data-pipeline` 鎖內跑）。

  python -m ntut_catalog merge --stage DIR --out data [--report PATH]

輸入是 fetch job 的 stage（`pipeline-result.json`＋`canonical/…`），輸出是就地更新的
**最新** data branch checkout（`{out}/canonical`）。順序：

  1. 只處理 `pipeline-result.json` 標記成功的 (資料集, 學期)；失敗者已寫出的部分檔一律不碰
     （Review Focus 2）。成功者也只收 `files` 中落在登錄表 `writes` 內的檔。
  2. catalog 品質檢查：課數 < HEAD 課數 × 0.95（env `QUALITY_MIN_RATIO` 可覆寫）或 0 課 →
     丟棄該學期這一筆（含同次爬取的人數快照）並告警，其他照常（Review Focus 1）。
     上游殘缺不可覆寫 canonical——否則隔天的比較基準也跟著壞。
  3. 覆寫 `writes` 檔；人數候選快照對 HEAD 去重（`enrollment_store.write_snapshot`），
     追加觀測紀錄（append_only）。
  4. 對合併後的 HEAD 計算 content_sha256，依 (資料集, 學期) 更新 `_meta/fetch-state.json`
     （hash 變了 `changed_at` 才前進）。

**所有「有沒有變」的判斷都在這裡、對最新 data branch 做**（Fable P1-4）：fetch job 的
checkout 可能已過期，daily 與 season 可能帶著舊基準先後進鎖。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ntut_catalog import enrollment_store, fetch_state, registry
from ntut_catalog.pipeline import RESULT_NAME

logger = logging.getLogger(__name__)

DEFAULT_MIN_RATIO = 0.95


def min_ratio_from_env() -> float:
    """與 publish 的品質閘門共用同一個 repo var `QUALITY_MIN_RATIO`；未設或空字串 → 0.95。"""
    raw = os.environ.get("QUALITY_MIN_RATIO", "").strip()
    if not raw:
        return DEFAULT_MIN_RATIO
    try:
        return float(raw)
    except ValueError as e:
        raise ValueError(f"invalid QUALITY_MIN_RATIO: {raw!r}") from e


@dataclass
class MergeReport:
    cadence: Optional[str] = None
    applied: List[Dict[str, object]] = field(default_factory=list)   # {name, term, changed}
    dropped: List[Dict[str, object]] = field(default_factory=list)   # {name, term, reason}
    alerts: List[Dict[str, object]] = field(default_factory=list)    # {name, term, message}
    snapshots_created: List[str] = field(default_factory=list)       # canonical 相對路徑

    @property
    def changed(self) -> bool:
        """內容是否真的改變（不算 checked_at 前進與觀測紀錄追加這種每次必有的 diff）。"""
        return any(a["changed"] for a in self.applied) or bool(self.snapshots_created)

    def datasets(self) -> List[str]:
        return sorted({str(a["name"]) for a in self.applied})

    def terms(self) -> List[str]:
        return sorted({str(a["term"]) for a in self.applied if a["term"]})

    def to_json(self) -> dict:
        d = asdict(self)
        d.update(changed=self.changed, datasets=self.datasets(), terms=self.terms())
        return d


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _safe_rel(rel: str) -> bool:
    p = Path(rel)
    return not p.is_absolute() and ".." not in p.parts and rel == p.as_posix()


def _is_snapshot(rel: str) -> bool:
    parts = rel.split("/")
    return (len(parts) == 3 and parts[1] == "enrollment"
            and parts[2].endswith(".ndjson") and parts[2] != enrollment_store.OBSERVATIONS)


def _catalog_quality(stage_canon: Path, canonical: Path, term: str,
                     min_ratio: float) -> Optional[str]:
    """catalog 課數檢查；不通過回傳原因。"""
    new = _count_lines(stage_canon / term / "catalog.ndjson")
    head = _count_lines(canonical / term / "catalog.ndjson")
    if new == 0:
        return f"catalog {term}: 0 課（上游未公布或解析失敗），不覆寫 canonical（HEAD {head} 課）"
    if head > 0 and new < head * min_ratio:
        return (f"catalog {term}: 課數 {new} < HEAD {head} × {min_ratio:.2f}，"
                f"疑似上游殘缺，不覆寫 canonical")
    return None


def merge_fetch_output(stage: Path, data_dir: Path,
                       result: Optional[dict] = None) -> MergeReport:
    """把 fetch job 的 stage 合併進最新的 `{data_dir}/canonical`，回傳合併報告。"""
    if result is None:
        result = json.loads((stage / RESULT_NAME).read_text(encoding="utf-8"))
    stage_canon = stage / "canonical"
    canonical = data_dir / "canonical"
    min_ratio = min_ratio_from_env()
    report = MergeReport(cadence=result.get("cadence"))
    state_path = fetch_state.path_for(canonical)
    state = fetch_state.load(state_path)

    for entry in result.get("datasets", []):
        name, term = entry["name"], entry.get("term")
        if not entry.get("ok"):
            report.dropped.append({"name": name, "term": term,
                                   "reason": f"fetch failed: {entry.get('error')}"})
            continue
        ds = registry.DATASETS.get(name)
        if ds is None:
            report.dropped.append({"name": name, "term": term, "reason": "unknown dataset"})
            report.alerts.append({"name": name, "term": term,
                                  "message": f"pipeline-result 有登錄表沒有的資料集 {name!r}"})
            continue
        files, rejected = _accepted_files(ds, term, entry.get("files") or [], stage_canon)
        for rel in rejected:
            report.alerts.append({"name": name, "term": term,
                                  "message": f"拒收 writes 以外或不存在的檔：{rel}"})
        if name == "catalog" and term:
            why = _catalog_quality(stage_canon, canonical, term, min_ratio)
            if why:
                logger.warning("[merge] %s", why)
                report.dropped.append({"name": name, "term": term, "reason": why})
                report.alerts.append({"name": name, "term": term, "message": why})
                continue
        snapshot_files = [f for f in files if _is_snapshot(f)]
        for rel in files:
            if rel in snapshot_files:
                continue
            dst = canonical / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage_canon / rel, dst)

        checked_at = entry["checked_at"]
        changed = False
        if ds.content:
            digest = fetch_state.content_hash(registry.content_files(canonical, ds, term), canonical)
            changed = fetch_state.update(state, name, term, digest, checked_at)
        enr = entry.get("enrollment")
        if enr and term:
            created = _merge_enrollment(stage_canon, canonical, term, enr, snapshot_files)
            if created:
                report.snapshots_created.append(created)
            _update_enrollment_state(state, canonical / term, term, checked_at)
        report.applied.append({"name": name, "term": term, "changed": changed})

    if report.applied:
        fetch_state.save(state_path, state)
    return report


def _accepted_files(ds: registry.Dataset, term: Optional[str], files: List[str],
                    stage_canon: Path) -> Tuple[List[str], List[str]]:
    ok, bad = [], []
    for rel in files:
        if (_safe_rel(rel) and registry.matches_any(rel, ds.writes, term)
                and (stage_canon / rel).is_file()):
            ok.append(rel)
        else:
            bad.append(rel)
    return ok, bad


def _merge_enrollment(stage_canon: Path, canonical: Path, term: str, enr: dict,
                      snapshot_files: List[str]) -> Optional[str]:
    """候選快照對 HEAD 去重＋追加觀測。回傳新寫出的快照（canonical 相對路徑），沒寫則 None。"""
    rel = f"{term}/enrollment/{enr['snapshot']}.ndjson"
    if rel not in snapshot_files:
        raise ValueError(f"enrollment observation 指向 stage 裡沒有的快照：{rel}")
    rows = [json.loads(line) for line in
            (stage_canon / rel).read_text(encoding="utf-8").splitlines() if line.strip()]
    term_dir = canonical / term
    name, created = enrollment_store.write_snapshot(term_dir, rows, enr["observed_at"])
    enrollment_store.append_observation(term_dir, enr["observed_at"], name)
    return f"{term}/enrollment/{name}.ndjson" if created else None


def _update_enrollment_state(state, term_dir: Path, term: str, checked_at: str) -> None:
    """fetch-state 的 `enrollment` 鍵：hash＝最新一份快照、changed_at＝最新快照的時間。"""
    snaps = enrollment_store.snapshots(term_dir)
    if not snaps:
        return
    newest = term_dir / "enrollment" / f"{snaps[-1]}.ndjson"
    digest = fetch_state.content_hash([newest], term_dir.parent)
    fetch_state.update(state, registry.ENROLLMENT_STATE_KEY, term, digest, checked_at,
                       changed_at=enrollment_store.stamp_to_iso(snaps[-1]))
