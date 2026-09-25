"""資料管線告警（spec §3「告警」）：開／更新／關閉 label `pipeline-alert` 的 issue。

兩種告警，各自一個 issue、各自自動關閉：

  run    `[pipeline] <workflow> 失敗`：任一 job 失敗、`pipeline-result.json` 有失敗的資料集、
         merge 報告有告警（例如 catalog 課數跌破門檻被丟棄）、publish 刪除保險觸發（exit 3）。
         下一次同 workflow 全部成功 → 留言並關閉。
  stale  `[pipeline] 資料過期：<dataset>`：`_meta/fetch-state.json` 中 cadence=daily 的資料集
         `checked_at` 超過 2 天、weekly 超過 9 天（取該資料集各學期中最新的一筆——只補爬過的
         舊學期不該讓整個資料集算過期）。恢復 → 關閉。由 daily 的 commit-publish job 呼叫。

用法：
  python infra/pipeline_alert.py run --workflow daily --run-url URL --needs-json "$NEEDS" \
      [--stages DIR] [--merge-reports DIR] [--publish-exit N] [--deletions-skipped P,…]
  python infra/pipeline_alert.py stale --data data
  python infra/pipeline_alert.py summary [--stages DIR] [--merge-reports DIR]   # 只寫 run summary 表

需要 gh CLI 與 GH_TOKEN（作法同 calendar_horizon_alert.py）。`PIPELINE_ALERT_DRY_RUN=1` → 只印
不動 issue（演練用）。告警本身失敗不該讓管線紅燈——workflow 以 continue-on-error 呼叫。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

LABEL = "pipeline-alert"
STALE_DAYS = {"daily": 2, "weekly": 9}
TAIPEI = dt.timezone(dt.timedelta(hours=8))

Gh = Callable[[List[str]], str]


def _gh(args: List[str]) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout.strip()


def _dry_gh(args: List[str]) -> str:
    print("[dry-run] gh " + " ".join(args))
    return "[]" if args[:2] == ["issue", "list"] else ""


def default_gh() -> Gh:
    return _dry_gh if os.environ.get("PIPELINE_ALERT_DRY_RUN", "").lower() in ("1", "true") else _gh


def find_issue(gh: Gh, title: str) -> Optional[str]:
    """開著的同標題 issue（精確比對標題；search 只是粗篩）。"""
    out = gh(["issue", "list", "--state", "open", "--label", LABEL, "--search",
              f"{title} in:title", "--json", "number,title"])
    for item in json.loads(out or "[]"):
        if item.get("title") == title:
            return str(item["number"])
    return None


def raise_issue(gh: Gh, title: str, body: str) -> str:
    """有開著的 → 留言更新；沒有 → 建 label（已存在就略過）再開新的。"""
    existing = find_issue(gh, title)
    if existing:
        gh(["issue", "comment", existing, "--body", body])
        print(f"updated #{existing}: {title}")
        return existing
    try:
        gh(["label", "create", LABEL, "--color", "B60205",
            "--description", "資料管線自動告警（infra/pipeline_alert.py）"])
    except subprocess.CalledProcessError:
        pass                                   # 已存在
    gh(["issue", "create", "--title", title, "--label", LABEL, "--body", body])
    print(f"opened: {title}")
    return "new"


def resolve_issue(gh: Gh, title: str, comment: str) -> Optional[str]:
    existing = find_issue(gh, title)
    if existing:
        gh(["issue", "comment", existing, "--body", comment])
        gh(["issue", "close", existing])
        print(f"closed #{existing}: {title}")
    return existing


# ------------------------------------------------------------------ run 失敗

def run_title(workflow: str) -> str:
    return f"[pipeline] {workflow} 失敗"


def collect_problems(needs: Dict[str, dict], stages: Optional[Path], merge_reports: Optional[Path],
                     publish_exit: Optional[int], deletions_skipped: str) -> List[str]:
    problems: List[str] = []
    for job, info in sorted(needs.items()):
        result = (info or {}).get("result")
        if result not in ("success", "skipped"):
            problems.append(f"job `{job}`：{result}")
    for p in sorted(stages.rglob("pipeline-result.json")) if stages and stages.exists() else []:
        for e in json.loads(p.read_text(encoding="utf-8")).get("datasets", []):
            if not e.get("ok"):
                problems.append(f"fetch 失敗 `{e.get('name')}` {e.get('term') or '_global'}："
                                f"{e.get('error')}")
    for p in sorted(merge_reports.rglob("merge-report*.json")) if merge_reports and merge_reports.exists() else []:
        for a in json.loads(p.read_text(encoding="utf-8")).get("alerts", []):
            problems.append(f"merge 告警 `{a.get('name')}` {a.get('term') or '_global'}："
                            f"{a.get('message')}")
    if publish_exit == 3:
        problems.append(f"R2 刪除保險觸發（已跳過刪除、其餘照常上線）：`{deletions_skipped or '?'}`"
                        "——確認刪除清單後以 maintenance republish 的 allow_mass_delete 放行")
    elif publish_exit not in (None, 0):
        problems.append(f"publish exit {publish_exit}")
    return problems


def cmd_run(args, gh: Gh) -> int:
    needs = json.loads(args.needs_json or "{}")
    publish_exit = int(args.publish_exit) if str(args.publish_exit or "").strip() else None
    problems = collect_problems(needs, args.stages, args.merge_reports, publish_exit,
                                args.deletions_skipped or "")
    title = run_title(args.workflow)
    if problems:
        body = (f"run：{args.run_url}\n\n" + "\n".join(f"- {p}" for p in problems)
                + "\n\n下一次同 workflow 全部成功時會自動關閉。")
        raise_issue(gh, title, body)
    else:
        resolve_issue(gh, title, f"{args.run_url} 全部成功，自動關閉。")
        print(f"{args.workflow}: no problems")
    return 0


# ------------------------------------------------------------------ 資料過期

def stale_title(dataset: str) -> str:
    return f"[pipeline] 資料過期：{dataset}"


def stale_datasets(state: dict, cadences: Dict[str, str], now: dt.datetime) -> Dict[str, Optional[str]]:
    """{dataset: 最新 checked_at 或 None}，只列出過期者。"""
    out: Dict[str, Optional[str]] = {}
    for name, cadence in sorted(cadences.items()):
        limit = STALE_DAYS.get(cadence)
        if limit is None:
            continue
        stamps = [e.get("checked_at") for e in (state.get("datasets", {}).get(name) or {}).values()]
        stamps = [s for s in stamps if s]
        latest = max(stamps, key=dt.datetime.fromisoformat) if stamps else None
        if latest is None or now - dt.datetime.fromisoformat(latest) > dt.timedelta(days=limit):
            out[name] = latest
    return out


def registry_cadences() -> Dict[str, str]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))
    from ntut_catalog.registry import DATASETS
    return {d.name: d.cadence for d in DATASETS.values() if d.content}


def cmd_stale(args, gh: Gh, cadences: Optional[Dict[str, str]] = None,
              now: Optional[dt.datetime] = None) -> int:
    path = args.data / "canonical" / "_meta" / "fetch-state.json"
    if not path.exists():
        print(f"{path} 不存在（尚未遷移？），skip")
        return 0
    state = json.loads(path.read_text(encoding="utf-8"))
    cadences = cadences if cadences is not None else registry_cadences()
    now = now or dt.datetime.now(TAIPEI)
    stale = stale_datasets(state, cadences, now)
    for name, cadence in sorted(cadences.items()):
        if cadence not in STALE_DAYS:
            continue
        title = stale_title(name)
        if name in stale:
            last = stale[name] or "從未"
            raise_issue(gh, title, (
                f"`{name}`（cadence={cadence}）最後一次成功確認來源：`{last}`，"
                f"超過 {STALE_DAYS[cadence]} 天。\n\n檢查 `{cadence}` workflow 最近的 run"
                "（排程沒觸發、fetch 失敗、或 merge 丟棄）。恢復後自動關閉。"))
        else:
            resolve_issue(gh, title, f"`{name}` 已恢復確認，自動關閉。")
    print(f"stale: {sorted(stale) or 'none'}")
    return 0


# ------------------------------------------------------------------ run summary

def render_summary(stages: Optional[Path], merge_reports: Optional[Path]) -> str:
    """各資料集 fetch／merge 結果表（寫進 $GITHUB_STEP_SUMMARY；Actions 列表看不出哪個資料集
    失敗，spec §3 的對策之一）。"""
    merged: Dict[tuple, str] = {}
    for p in sorted(merge_reports.rglob("merge-report*.json")) if merge_reports and merge_reports.exists() else []:
        r = json.loads(p.read_text(encoding="utf-8"))
        for a in r.get("applied", []):
            merged[(a["name"], a.get("term"))] = "內容有變" if a.get("changed") else "已確認、未變"
        for d in r.get("dropped", []):
            merged[(d["name"], d.get("term"))] = f"丟棄：{d.get('reason')}"
    lines = ["## 資料集", "", "| 資料集 | 學期 | fetch | merge |", "|---|---|---|---|"]
    for p in sorted(stages.rglob("pipeline-result.json")) if stages and stages.exists() else []:
        for e in json.loads(p.read_text(encoding="utf-8")).get("datasets", []):
            key = (e.get("name"), e.get("term"))
            fetch = "✅" if e.get("ok") else f"❌ {e.get('error')}"
            lines.append(f"| {key[0]} | {key[1] or '_global'} | {fetch} | {merged.get(key, '—')} |")
    return "\n".join(lines) + "\n"


def cmd_summary(args) -> int:
    text = render_summary(args.stages, args.merge_reports)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    print(text, end="")
    return 0


def main(argv: Optional[List[str]] = None, gh: Optional[Gh] = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline_alert")
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run 失敗告警")
    r.add_argument("--workflow", required=True)
    r.add_argument("--run-url", required=True)
    r.add_argument("--needs-json", default="{}", help="workflow 的 toJSON(needs)")
    r.add_argument("--stages", type=Path, default=None, help="fetch stage artifact 目錄（找 pipeline-result.json）")
    r.add_argument("--merge-reports", type=Path, default=None, help="merge 報告目錄")
    r.add_argument("--publish-exit", default=None)
    r.add_argument("--deletions-skipped", default="")
    sm = sub.add_parser("summary", help="資料集結果表 → $GITHUB_STEP_SUMMARY（不動 issue）")
    sm.add_argument("--stages", type=Path, default=None)
    sm.add_argument("--merge-reports", type=Path, default=None)
    s = sub.add_parser("stale", help="資料過期告警（讀 fetch-state）")
    s.add_argument("--data", type=Path, default=Path("data"))
    args = ap.parse_args(argv)
    if args.command == "summary":
        return cmd_summary(args)
    gh = gh or default_gh()
    if args.command == "run":
        return cmd_run(args, gh)
    return cmd_stale(args, gh)


if __name__ == "__main__":
    sys.exit(main())
