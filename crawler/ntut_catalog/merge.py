"""commit-publish job 的合併邏輯（spec §3 job 2；在 `concurrency: data-pipeline` 鎖內跑）。

  python -m ntut_catalog merge --stage DIR --out data [--report PATH]

輸入是 fetch job 的 stage（`pipeline-result.json`＋`canonical/…`），輸出是就地更新的
**最新** data branch checkout（`{out}/canonical`）。順序：

  1. 只處理 `pipeline-result.json` 標記成功的 (資料集, 學期)；失敗者已寫出的部分檔一律不碰
     （Review Focus 2）。成功者也只收 `files` 中落在登錄表 `writes` 內的檔。
  2. 節點失敗（`failed_nodes`，spec §3「節點失敗的處理」）：失敗節點 > node_total × 5%
     （env `PARTIAL_FAILURE_MAX_RATIO` 可覆寫）→ 丟棄整筆；catalog 有任何失敗節點 → 丟棄該學期
     （含人數快照）；standards／mprograms／details → 失敗節點逐一從 HEAD 沿用前一版，HEAD 也
     沒有的列為缺漏，發 warning 告警。
  3. catalog 品質檢查：課數 < HEAD 課數 × 0.95（env `QUALITY_MIN_RATIO` 可覆寫）或 0 課 →
     丟棄該學期這一筆（含同次爬取的人數快照）並告警，其他照常（Review Focus 1）。
     上游殘缺不可覆寫 canonical——否則隔天的比較基準也跟著壞。
  4. 覆寫 `writes` 檔；人數候選快照對 HEAD 去重（`enrollment_store.write_snapshot`），
     追加觀測紀錄（append_only）。
  5. 對合併後的 HEAD 計算 content_sha256，依 (資料集, 學期) 更新 `_meta/fetch-state.json`
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
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ntut_catalog import enrollment_store, fetch_state, registry
from ntut_catalog.pipeline import RESULT_NAME

logger = logging.getLogger(__name__)

DEFAULT_MIN_RATIO = 0.95
# 單筆 (資料集, 學期) 失敗節點占比的上限：超過就整筆丟棄（保留 HEAD），不做節點沿用——
# 失敗這麼多通常是學校整段不通，沿用大量舊資料等於假裝有爬到。
DEFAULT_PARTIAL_FAILURE_MAX_RATIO = 0.05


def min_ratio_from_env() -> float:
    """與 publish 的品質閘門共用同一個 repo var `QUALITY_MIN_RATIO`；未設或空字串 → 0.95。"""
    raw = os.environ.get("QUALITY_MIN_RATIO", "").strip()
    if not raw:
        return DEFAULT_MIN_RATIO
    try:
        return float(raw)
    except ValueError as e:
        raise ValueError(f"invalid QUALITY_MIN_RATIO: {raw!r}") from e


def partial_max_ratio_from_env() -> float:
    """env `PARTIAL_FAILURE_MAX_RATIO`；未設或空字串 → 0.05。"""
    raw = os.environ.get("PARTIAL_FAILURE_MAX_RATIO", "").strip()
    if not raw:
        return DEFAULT_PARTIAL_FAILURE_MAX_RATIO
    try:
        return float(raw)
    except ValueError as e:
        raise ValueError(f"invalid PARTIAL_FAILURE_MAX_RATIO: {raw!r}") from e


@dataclass
class MergeReport:
    cadence: Optional[str] = None
    # {name, term, changed}；部分節點失敗、從 HEAD 沿用者另加 partial=True、failed_nodes=<數量>
    applied: List[Dict[str, object]] = field(default_factory=list)
    dropped: List[Dict[str, object]] = field(default_factory=list)   # {name, term, reason}
    alerts: List[Dict[str, object]] = field(default_factory=list)    # {name, term, level, message}
    snapshots_created: List[str] = field(default_factory=list)       # canonical 相對路徑
    # {name, term, failed, node_total, carried_forward: [node], missing: [node]}
    partial: List[Dict[str, object]] = field(default_factory=list)

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


def _alert(report: MergeReport, name: str, term: Optional[str], message: str,
           level: str = "error") -> None:
    report.alerts.append({"name": name, "term": term, "level": level, "message": message})


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
    max_ratio = partial_max_ratio_from_env()
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
            _alert(report, name, term, f"pipeline-result 有登錄表沒有的資料集 {name!r}")
            continue
        files, rejected = _accepted_files(ds, term, entry.get("files") or [], stage_canon)
        for rel in rejected:
            _alert(report, name, term, f"拒收 writes 以外或不存在的檔：{rel}")
        failed_nodes = list(entry.get("failed_nodes") or [])
        spliced: Dict[str, bytes] = {}
        if failed_nodes:
            why = _partial_drop_reason(name, term, failed_nodes, entry.get("node_total"),
                                       max_ratio)
            if why:
                logger.warning("[merge] %s", why)
                report.dropped.append({"name": name, "term": term, "reason": why})
                _alert(report, name, term, why)
                continue
            # 對 HEAD（尚未覆寫）取失敗節點的前一版，拼進本次的新檔
            spliced, carried, missing = _SPLICERS[name](stage_canon, canonical, term,
                                                        failed_nodes, files)
            report.partial.append({"name": name, "term": term, "failed": len(failed_nodes),
                                   "node_total": entry.get("node_total"),
                                   "carried_forward": carried, "missing": missing})
            msg = _partial_message(name, term, failed_nodes, entry.get("node_total"),
                                   carried, missing)
            logger.warning("[merge] %s", msg)
            _alert(report, name, term, msg, level="warning")
        if name == "catalog" and term:
            why = _catalog_quality(stage_canon, canonical, term, min_ratio)
            if why:
                logger.warning("[merge] %s", why)
                report.dropped.append({"name": name, "term": term, "reason": why})
                _alert(report, name, term, why)
                continue
        snapshot_files = [f for f in files if _is_snapshot(f)]
        for rel in files:
            if rel in snapshot_files:
                continue
            dst = canonical / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if rel in spliced:
                dst.write_bytes(spliced[rel])
            else:
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
        applied: Dict[str, object] = {"name": name, "term": term, "changed": changed}
        if failed_nodes:
            # 資料集確實確認過（checked_at 照常前進），但有節點沿用舊版——報告裡標出來
            applied.update(partial=True, failed_nodes=len(failed_nodes))
        report.applied.append(applied)

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


# ------------------------------------------------------------------ 節點失敗（spec §3）

def node_label(node: Dict[str, object]) -> str:
    """`{"year": 115, "matric": "7", "division": "59"}` → `year=115/matric=7/division=59`。"""
    return "/".join(f"{k}={v}" for k, v in node.items())


def _labels(nodes: Sequence[Dict[str, object]]) -> str:
    return "、".join(node_label(n) for n in nodes) or "無"


def _partial_drop_reason(name: str, term: Optional[str], failed: List[Dict[str, object]],
                         node_total: Optional[int], max_ratio: float) -> Optional[str]:
    """失敗太多、catalog、或沒有沿用規則的資料集 → 整筆丟棄的原因；可以逐節點沿用則 None。"""
    label = f"{name} {term or '_global'}"
    total = node_total or 0
    if total <= 0 or len(failed) > total * max_ratio:
        return (f"{label}: {len(failed)}/{total or '?'} 個節點失敗，超過 {max_ratio:.0%}，"
                f"整筆不覆寫 canonical（保留 HEAD）。失敗節點：{_labels(failed)}")
    if name not in _SPLICERS:
        # catalog 不做節點拼接：一個系所的課整段消失，比例檢查（0.95）抓不到，只能整學期保留 HEAD
        return (f"{label}: {len(failed)}/{total} 個節點失敗，此資料集不做節點沿用，"
                f"整學期不覆寫 canonical（保留 HEAD，含同次人數快照）。失敗節點：{_labels(failed)}")
    return None


def _partial_message(name: str, term: Optional[str], failed: List[Dict[str, object]],
                     node_total: Optional[int], carried: List[Dict[str, object]],
                     missing: List[Dict[str, object]]) -> str:
    text = (f"{name} {term or '_global'}: {len(failed)}/{node_total} 個節點失敗，"
            f"已從 HEAD 沿用 {len(carried)} 個：{_labels(carried)}")
    if missing:
        text += f"；HEAD 也沒有、本次缺漏 {len(missing)} 個：{_labels(missing)}"
    return text


def _splice_in_head_order(new: List, head: List, carry: set, key: Callable) -> List:
    """把 HEAD 中鍵在 `carry` 的項目插回 `new`，位置緊接在它於 HEAD 的前一個（仍存在的）項目之後。

    fetcher 依上游清單順序寫出（不排序），所以只能以 HEAD 的相對順序定位：除了失敗節點以外
    都沒變時，結果與 HEAD 逐項相同（逐位元組相同的前提）。
    """
    out = list(new)

    def pos(k) -> Optional[int]:
        return next((i for i, x in enumerate(out) if key(x) == k), None)

    prev = None
    for item in head:
        k = key(item)
        if k in carry:
            out.insert(0 if prev is None else pos(prev) + 1, item)
            prev = k
        elif pos(k) is not None:
            prev = k
    return out


Spliced = Tuple[Dict[str, bytes], List[Dict[str, object]], List[Dict[str, object]]]


def _splice_standards(stage_canon: Path, canonical: Path, term: Optional[str],
                      failed: List[Dict[str, object]], files: List[str]) -> Spliced:
    """standards/{year}.json 內以 (matric, division) 為鍵；-3 失敗（只有 matric）沿用該學制全部系所。"""
    from models import StandardDirectory

    out: Dict[str, bytes] = {}
    carried: List[Dict[str, object]] = []
    missing: List[Dict[str, object]] = []
    for year in sorted({n["year"] for n in failed}, key=str):
        nodes = [n for n in failed if n["year"] == year]
        rel = f"standards/{year}.json"
        head_path = canonical / rel
        if rel not in files or not head_path.is_file():
            missing += nodes
            continue
        new = StandardDirectory.model_validate_json((stage_canon / rel).read_text(encoding="utf-8"))
        head = StandardDirectory.model_validate_json(head_path.read_text(encoding="utf-8"))
        new_keys = {(p.matric, p.division) for p in new.programs}
        carry: set = set()
        for n in nodes:
            hits = {(p.matric, p.division) for p in head.programs
                    if p.matric == n["matric"] and ("division" not in n or p.division == n["division"])}
            hits -= new_keys
            (carried if hits else missing).append(n)
            carry |= hits
        if carry:
            new.programs = _splice_in_head_order(new.programs, head.programs, carry,
                                                 lambda p: (p.matric, p.division))
            out[rel] = new.model_dump_json().encode("utf-8")
    return out, carried, missing


def _splice_mprograms(stage_canon: Path, canonical: Path, term: Optional[str],
                      failed: List[Dict[str, object]], files: List[str]) -> Spliced:
    """{term}/mprograms.json 以學程 code 為鍵。失敗的只有 Cprog -4（課程標準＋規定原文），
    所以只沿用 HEAD 該學程的 `courses`／`rules_text`；`offering_ids`、`name` 來自本次成功的請求。"""
    from models import MicroProgramDirectory

    rel = f"{term}/mprograms.json"
    head_path = canonical / rel
    if rel not in files or not head_path.is_file():
        return {}, [], list(failed)
    new = MicroProgramDirectory.model_validate_json((stage_canon / rel).read_text(encoding="utf-8"))
    head = {p.code: p for p in MicroProgramDirectory.model_validate_json(
        head_path.read_text(encoding="utf-8")).programs}
    carried: List[Dict[str, object]] = []
    missing: List[Dict[str, object]] = []
    wanted = {n["program"]: n for n in failed}
    for i, prog in enumerate(new.programs):
        if prog.code not in wanted:
            continue
        prev = head.get(prog.code)
        if prev is None:
            continue
        new.programs[i] = prog.model_copy(update={"courses": prev.courses,
                                                  "rules_text": prev.rules_text})
        carried.append(wanted.pop(prog.code))
    missing = list(wanted.values())       # HEAD 沒有：保留本次降級的版本（courses=[]）
    out = {rel: new.model_dump_json().encode("utf-8")} if carried else {}
    return out, carried, missing


def _splice_details(stage_canon: Path, canonical: Path, term: Optional[str],
                    failed: List[Dict[str, object]], files: List[str]) -> Spliced:
    """{term}/details.ndjson 以 offering_id 為鍵：失敗的課號整行換成 HEAD 那一行（原樣位元組）；
    HEAD 沒有 → 這一行不寫（描述／大綱不完整的一行比沒有更會誤導）。"""
    rel = f"{term}/details.ndjson"
    if rel not in files:
        return {}, [], list(failed)
    head_path = canonical / rel
    head: Dict[str, str] = {}
    if head_path.is_file():
        for line in head_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                head[json.loads(line)["offering_id"]] = line
    wanted = {n["offering_id"]: n for n in failed}
    carried: List[Dict[str, object]] = []
    missing: List[Dict[str, object]] = []
    lines: List[str] = []
    for line in (stage_canon / rel).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        oid = json.loads(line)["offering_id"]
        if oid not in wanted:
            lines.append(line)
        elif oid in head:
            lines.append(head[oid])
            carried.append(wanted.pop(oid))
        else:
            missing.append(wanted.pop(oid))
    missing += list(wanted.values())      # 失敗但本次檔裡也沒有這一行
    return {rel: "".join(x + "\n" for x in lines).encode("utf-8")}, carried, missing


# 可逐節點沿用的資料集；不在此表者（catalog）有失敗節點一律整筆丟棄
_SPLICERS: Dict[str, Callable[..., Spliced]] = {
    "standards": _splice_standards,
    "mprograms": _splice_mprograms,
    "details": _splice_details,
}
