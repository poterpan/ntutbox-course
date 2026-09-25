"""fetch job 的入口：依 cadence 跑登錄表裡的資料集（spec §2、§3 job 1）。

  python -m ntut_catalog pipeline --cadence daily [--datasets a,b] [--terms …] --out data [--stage DIR]

- 每個 (資料集, 學期) 獨立 try：一個失敗記進 `pipeline-result.json`，不中斷其他。
- fetcher 直接寫 `--out` 的 canonical（fetch job 的 data branch checkout；增量判斷要讀它），
  跑完把**成功者回報的檔**複製到 `--stage`，連同 `pipeline-result.json` 交給 merge。
- **不在這裡判斷內容有沒有變**——這份 checkout 可能已過期；那是上鎖的 merge 對最新 HEAD 做的事。
- 逐節點爬取的資料集把重試後仍失敗的節點記在 `failed_nodes`（＋`node_total`）；單一節點失敗
  不讓整個資料集失敗，丟棄或從 HEAD 沿用由 merge 決定（spec §3「節點失敗的處理」）。

`--stage` 佈局（整個目錄就是 workflow 上傳的 artifact）：
  {stage}/pipeline-result.json
  {stage}/canonical/<與 data branch 相同的相對路徑>
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from ntut_catalog import registry
from ntut_catalog.registry import FetchContext

logger = logging.getLogger(__name__)

RESULT_NAME = "pipeline-result.json"
RESULT_SCHEMA_VERSION = 1


class UsageError(ValueError):
    """呼叫方式錯誤（CLI exit 2）：例如 season 沒帶學期。"""


@dataclass
class PipelineResult:
    cadence: str
    datasets: List[Dict[str, object]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(e["ok"] for e in self.datasets)

    def to_json(self) -> dict:
        return {"schema_version": RESULT_SCHEMA_VERSION, "cadence": self.cadence,
                "datasets": self.datasets}


def select_datasets(cadence: str, names: Optional[Sequence[str]]) -> List[registry.Dataset]:
    """`--datasets` 未給 → 該 cadence 的全部；給了 → 只跑指定的（可跨 cadence，供 backfill）。"""
    if not names:
        return registry.for_cadence(cadence)
    unknown = [n for n in names if n not in registry.DATASETS]
    if unknown:
        raise UsageError(f"unknown datasets: {unknown}（可用：{sorted(registry.DATASETS)}）")
    return [registry.DATASETS[n] for n in names]


def run(cadence: str, datasets: Optional[Sequence[str]], terms: Sequence[str], out: Path,
        stage: Path, ctx: Optional[FetchContext] = None,
        current_term: Optional[Callable[[], str]] = None) -> PipelineResult:
    """跑一輪 fetch，寫 `{stage}/pipeline-result.json` 並回傳結果。"""
    if cadence == "season" and not terms:
        # 12 月 115-2 網路選課時 current-term 可能仍是 115-1——默默用它會刷錯學期（Review Focus 5）。
        raise UsageError("cadence=season 必須明確指定 --terms（current-term 在選課季可能是錯的學期）")
    selected = select_datasets(cadence, datasets)
    ctx = ctx or FetchContext(out)
    result = PipelineResult(cadence=cadence)

    detected: Dict[str, str] = {}

    def _current() -> str:
        # 失敗也記住：學校不通時每個資料集各自重試 5 次（每次約 5 分鐘）只是白等。
        if "error" in detected:
            raise RuntimeError(f"current-term 偵測已失敗（沿用首次錯誤）：{detected['error']}")
        if "v" not in detected:
            try:
                if current_term is not None:
                    detected["v"] = current_term()
                else:
                    from ntut_catalog.client import detect_current_term
                    detected["v"] = detect_current_term(ctx.catalog_client)
            except Exception as e:  # noqa: BLE001 — 交給呼叫端記成該資料集失敗
                detected["error"] = _summary(e)
                raise
            logger.info("current term: %s", detected["v"])
        return detected["v"]

    try:
        for ds in selected:
            try:
                term_list = registry.resolve_terms(ds.terms, terms, _current)
            except Exception as e:  # noqa: BLE001 — 學校不通時 current-term 會失敗；其他資料集照跑
                logger.exception("[%s] resolve terms failed", ds.name)
                result.datasets.append(_entry(ds.name, None, ok=False, error=_summary(e)))
                continue
            for term in term_list:
                logger.info("[%s] %s fetching ...", ds.name, term or "_global")
                try:
                    output = ds.fetch(ctx, term)
                    _check_files(ds, term, output.files)
                except Exception as e:  # noqa: BLE001 — 每個 (資料集, 學期) 獨立失敗
                    logger.exception("[%s] %s failed", ds.name, term or "_global")
                    result.datasets.append(_entry(ds.name, term, ok=False, error=_summary(e)))
                    continue
                entry = _entry(ds.name, term, ok=True, checked_at=ctx.now_iso(),
                               files=sorted(set(output.files)),
                               failed_nodes=output.failed_nodes, node_total=output.node_total)
                entry.update(output.extra)
                if output.failed_nodes:
                    logger.warning("[%s] %s: %d/%s 個節點重試後仍失敗（交給 merge 處理）：%s",
                                   ds.name, term or "_global", len(output.failed_nodes),
                                   output.node_total, output.failed_nodes)
                result.datasets.append(entry)
    finally:
        ctx.close()

    _write_stage(out / "canonical", stage, result)
    return result


def _entry(name: str, term: Optional[str], ok: bool, checked_at: Optional[str] = None,
           error: Optional[str] = None, files: Optional[List[str]] = None,
           failed_nodes: Optional[List[Dict[str, object]]] = None,
           node_total: Optional[int] = None) -> Dict[str, object]:
    """`failed_nodes`／`node_total`：逐節點爬取的資料集才有 node_total（其餘 None）；
    ok=True 但 failed_nodes 非空＝「部分成功」，由 merge 決定丟棄或從 HEAD 沿用。"""
    return {"name": name, "term": term, "ok": ok, "checked_at": checked_at, "error": error,
            "files": files or [], "failed_nodes": list(failed_nodes or []),
            "node_total": node_total}


def _summary(e: BaseException) -> str:
    text = f"{type(e).__name__}: {e}"
    return text if len(text) <= 500 else text[:497] + "..."


def _check_files(ds: registry.Dataset, term: Optional[str], files: Sequence[str]) -> None:
    """fetcher 回報的檔必須落在登錄表 `writes` 內——否則 merge 會拒收，不如在這裡就失敗。"""
    bad = [f for f in files if not registry.matches_any(f, ds.writes, term)]
    if bad:
        raise RuntimeError(f"{ds.name} 回報了 writes 以外的檔：{bad}")


def _write_stage(canonical: Path, stage: Path, result: PipelineResult) -> None:
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "canonical").mkdir(parents=True)
    for entry in result.datasets:
        if not entry["ok"]:
            continue
        for rel in entry["files"]:
            dst = stage / "canonical" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(canonical / rel, dst)
    (stage / RESULT_NAME).write_text(
        json.dumps(result.to_json(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
