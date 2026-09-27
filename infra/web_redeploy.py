"""資料發佈後要不要觸發 web 重新部署（D22）。

`/browse/**` hub 是 build 期產生的靜態頁（apps/web/src/lib/hub/build-catalog.ts）：課程清單凍結在
最後一次 build 的資料。所以 publish 成功後，若這次 merge 讓**預設學期**的 catalog 內容有變，
就 POST Workers Builds Deploy Hook 重新 build。本檔只做決策；curl 由 commit-publish action 的
shell step 做（hook URL 是憑證，只經 secret → env，不進 Python 參數或 log）。

預設學期：`data/v1/manifest.json` 的 `term_schedule.default`（`[{term, from}]`，`from`＝該學期成為
預設的時刻）中 `from ≤ now` 且最晚的一筆；該學期還沒有 catalog → 本學期 → `terms` 最新者（與 web
`resolveTerms` 相同，D21——hub 實際建的就是這個學期）。manifest 沒有 `term_schedule`、或沒有已生效的項目 →
解析不出來 → 退而求其次：**任一學期**的 catalog 有變就重新部署（簡單、寧可多 build；Deploy Hook
在已排隊時會去重，多觸發的代價只是一次 build）。

只看 merge 報告的 `applied[]` 裡 `name == "catalog"` 且 `changed` 為真者——hub 只列課程目錄；
人數快照、課綱等變動不影響 hub。沒有 merge 報告（republish）→ 不部署。
預設學期的切換本身（`from` 那一刻）由 season-scheduler Worker 觸發，不在這裡。

用法：
  python infra/web_redeploy.py --merge-reports DIR --manifest data/v1/manifest.json [--now ISO]
輸出：stdout 一行理由；有 `$GITHUB_OUTPUT` 時寫 `redeploy=true|false` 與 `reason=…`。永遠 exit 0。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple

TAIPEI = dt.timezone(dt.timedelta(hours=8))
HUB_DATASET = "catalog"


def changed_catalog_terms(merge_reports: Optional[Path]) -> Set[str]:
    """merge 報告中 catalog 內容有變的學期。"""
    out: Set[str] = set()
    if not merge_reports or not merge_reports.exists():
        return out
    for p in sorted(merge_reports.rglob("merge-report*.json")):
        for a in json.loads(p.read_text(encoding="utf-8")).get("applied", []):
            if a.get("name") == HUB_DATASET and a.get("changed") and a.get("term"):
                out.add(str(a["term"]))
    return out


def _effective(entries, now: dt.datetime) -> Optional[str]:
    """`[{term, from}]` 中已生效（from ≤ now）且最晚的學期；沒有 → None。"""
    if not isinstance(entries, list):
        return None
    best: Optional[Tuple[dt.datetime, str]] = None
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("term"), str):
            continue
        try:
            since = dt.datetime.fromisoformat(str(e.get("from")))
        except ValueError:
            continue
        if since.tzinfo is None:
            since = since.replace(tzinfo=TAIPEI)
        if since <= now and (best is None or since > best[0]):
            best = (since, e["term"])
    return best[1] if best else None


def _containing_term(now: dt.datetime) -> str:
    """台北日期所在學期（與 term_calendar._containing_term、web containingTerm 同規則）。"""
    d = now.astimezone(TAIPEI).date()
    if d.month >= 8:
        return f"{d.year - 1911}-1"
    if d.month == 1:
        return f"{d.year - 1912}-1"
    return f"{d.year - 1912}-2"


def _term_order(term: str) -> Tuple[int, int]:
    try:
        y, s = term.split("-")
        return int(y), int(s)
    except ValueError:
        return (-1, -1)


def resolve_default_term(manifest: Optional[dict], now: dt.datetime) -> Optional[str]:
    """hub 會建的學期——與 web `resolveTerms`（apps/web/src/lib/terms/term-schedule.ts）同語意：

    `term_schedule.default` 已生效且最晚的一筆；該學期不在 `manifest.terms`（還沒有 catalog）→
    本學期（`term_schedule.current`，無則日期規則）；本學期也不在 → `terms` 最新者。
    解析不出預設學期（無 `term_schedule`／沒有已生效的項目）→ None（呼叫端退為「任一學期有變就部署」）。
    manifest 沒有 `terms` 鍵時不做 catalog 存在檢查。
    """
    ts = (manifest or {}).get("term_schedule")
    if not isinstance(ts, dict):
        return None
    raw = _effective(ts.get("default"), now)
    if raw is None:
        return None
    terms = (manifest or {}).get("terms")
    if not isinstance(terms, dict) or raw in terms:
        return raw
    current = _effective(ts.get("current"), now) or _containing_term(now)
    if current in terms:
        return current
    return max(terms, key=_term_order) if terms else None


def decide(changed: Set[str], default_term: Optional[str]) -> Tuple[bool, str]:
    if not changed:
        return False, "catalog 沒有內容變動"
    terms = ",".join(sorted(changed))
    if default_term is None:
        return True, f"預設學期解析不出（manifest 無 term_schedule），任一學期 catalog 有變：{terms}"
    if default_term in changed:
        return True, f"預設學期 {default_term} 的 catalog 有變"
    return False, f"catalog 有變的是 {terms}，不是預設學期 {default_term}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="web_redeploy")
    ap.add_argument("--merge-reports", type=Path, default=None)
    ap.add_argument("--manifest", type=Path, default=Path("data/v1/manifest.json"))
    ap.add_argument("--now", default=None, help="ISO 時間（測試用）；預設現在")
    args = ap.parse_args(argv)
    now = dt.datetime.fromisoformat(args.now) if args.now else dt.datetime.now(TAIPEI)
    manifest = None
    if args.manifest.exists():
        try:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        except ValueError:
            manifest = None
    redeploy, reason = decide(changed_catalog_terms(args.merge_reports),
                              resolve_default_term(manifest, now))
    print(f"web redeploy: {'yes' if redeploy else 'no'} — {reason}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"redeploy={'true' if redeploy else 'false'}\nreason={reason}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
