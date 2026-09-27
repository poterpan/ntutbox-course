"""資料管線告警（spec §3「告警」）：開／更新／關閉 label `pipeline-alert` 的 issue。

兩種告警，各自一個 issue、各自自動關閉：

  run    `[pipeline] <workflow> 失敗`：任一 job 失敗、`pipeline-result.json` 有失敗的資料集、
         merge 報告有告警（例如 catalog 課數跌破門檻被丟棄；部分節點失敗、已從 HEAD 沿用者，以及
         非當前學期課數／人數驟減但照樣採用者（D20）是 warning 等級，同樣列進 issue——要有人知道）、publish 刪除保險觸發（exit 3）、
         web 重新部署的 Deploy Hook 失敗（D22；不擋資料上線，但 hub 會停在舊資料）。
         下一次同 workflow 全部成功 → 留言並關閉。
  stale  `[pipeline] 資料過期：<dataset>`：`_meta/fetch-state.json` 中 cadence=daily 的資料集
         `checked_at` 超過 2 天、weekly 超過 9 天（取該資料集各學期中最新的一筆——只補爬過的
         舊學期不該讓整個資料集算過期）。恢復 → 關閉。由 daily 的 commit-publish job 呼叫。

season 排程（`data/ops/season-schedule.json`，derive 產；issue #111）另有兩種，同樣由 daily 呼叫：

  season-catalog    `[pipeline] season 窗口學期缺 catalog：<term>`：排程裡的學期在未來
                    SEASON_CATALOG_LEAD_DAYS 天內有觸發格、但 canonical 沒有 `{term}/catalog.ndjson`
                    → season 一定會失敗（fetch_enrollment 要先有 catalog）。正常情況 daily 在窗口
                    30 天前就自動納入該學期（D19），這是安全網。補上（或窗口過了）→ 關閉。
  season-freshness  `[pipeline] season 未依排程執行`：`at` 落在 [now−12h, now−1h] 的觸發格，
                    每個學期都要有 `observed_at` 在 [at, at+1h) 的觀測紀錄；缺任何一格 → 開／更新，
                    全部對上（或窗口內沒有觸發格）→ 關閉。now 用 daily 自己的時間（GitHub cron
                    延遲幾小時也沒關係，窗口是相對的）。

GIS 快照 updateSequence 記錄（D23、#120）由 weekly 的 alert job 呼叫——**只記錄、不開 issue**：

  gis-drift         學校 GeoServer WFS GetCapabilities 的 updateSequence 與 repo 快照
                    `crawler/ntut_catalog/reference/gis-rooms.json` 的值寫進 run summary＋`::notice`。
                    updateSequence 會因與教室無關的變動前進，不能當告警依據（長期見 issue #120）。
                    只打 1 個請求；學校憑證鏈 Python 驗不過時對這一個公開唯讀 URL 不驗證重試一次（log 註記）；
                    其他失敗只發 warning。

用法：
  python infra/pipeline_alert.py run --workflow daily --run-url URL --needs-json "$NEEDS" \
      [--stages DIR] [--merge-reports DIR] [--publish-exit N] [--deletions-skipped P,…] \
      [--web-redeploy STATUS]
  python infra/pipeline_alert.py stale --data data
  python infra/pipeline_alert.py season-catalog --data data
  python infra/pipeline_alert.py season-freshness --data data
  python infra/pipeline_alert.py gis-drift [--snapshot PATH]
  python infra/pipeline_alert.py summary [--stages DIR] [--merge-reports DIR]   # 只寫 run summary 表

需要 gh CLI 與 GH_TOKEN（作法同 calendar_horizon_alert.py）。`PIPELINE_ALERT_DRY_RUN=1` → 只印
不動 issue（演練用）。告警本身失敗不該讓管線紅燈——workflow 以 continue-on-error 呼叫。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

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
                     publish_exit: Optional[int], deletions_skipped: str,
                     web_redeploy: str = "") -> List[str]:
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
            kind = "merge 警告" if a.get("level") == "warning" else "merge 告警"
            problems.append(f"{kind} `{a.get('name')}` {a.get('term') or '_global'}："
                            f"{a.get('message')}")
    if publish_exit == 3:
        problems.append(f"R2 刪除保險觸發（已跳過刪除、其餘照常上線）：`{deletions_skipped or '?'}`"
                        "——確認刪除清單後以 maintenance republish 的 allow_mass_delete 放行")
    elif publish_exit not in (None, 0):
        problems.append(f"publish exit {publish_exit}")
    if web_redeploy.startswith("failed"):
        problems.append(f"web 重新部署（Deploy Hook）{web_redeploy}——資料已上線，但 `/browse/**` hub "
                        "停在上一次 build；到 Cloudflare dashboard 手動 Retry deployment，"
                        "或檢查 secret `WEB_DEPLOY_HOOK_URL`（見 infra/README.md）")
    return problems


def cmd_run(args, gh: Gh) -> int:
    needs = json.loads(args.needs_json or "{}")
    publish_exit = int(args.publish_exit) if str(args.publish_exit or "").strip() else None
    problems = collect_problems(needs, args.stages, args.merge_reports, publish_exit,
                                args.deletions_skipped or "", args.web_redeploy or "")
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


# ------------------------------------------------------------------ season 排程（issue #111）

SEASON_SCHEDULE_REL = "ops/season-schedule.json"
SEASON_CATALOG_PREFIX = "[pipeline] season 窗口學期缺 catalog："
# 只對「快到了」的窗口告警：下學期的課程目錄要等學校公布（通常選課前數週），
# 太早開 issue 只是噪音、也無從處理。
SEASON_CATALOG_LEAD_DAYS = 14
SEASON_FRESHNESS_TITLE = "[pipeline] season 未依排程執行"
FRESHNESS_LOOKBACK = dt.timedelta(hours=12)
FRESHNESS_GRACE = dt.timedelta(hours=1)        # 觸發後給 run 跑完的時間
OBSERVATION_TOLERANCE = dt.timedelta(hours=1)  # 觀測時間須落在 [at, at+1h)


def season_catalog_title(term: str) -> str:
    return f"{SEASON_CATALOG_PREFIX}{term}"


def load_season_schedule(data: Path) -> Optional[dict]:
    path = data / SEASON_SCHEDULE_REL
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _slot_terms(slot: dict) -> List[str]:
    return [t for t in str(slot.get("terms") or "").split(",") if t]


def open_titles_with_prefix(gh: Gh, prefix: str) -> List[str]:
    out = gh(["issue", "list", "--state", "open", "--label", LABEL, "--search",
              f"{prefix} in:title", "--json", "number,title"])
    return sorted(i["title"] for i in json.loads(out or "[]") if i.get("title", "").startswith(prefix))


def season_terms_missing_catalog(schedule: dict, canonical: Path,
                                 now: dt.datetime) -> Dict[str, str]:
    """{term: 最近一個觸發格}：未來 LEAD 天內有觸發格、但沒有 catalog.ndjson 的學期。"""
    horizon = now + dt.timedelta(days=SEASON_CATALOG_LEAD_DAYS)
    out: Dict[str, str] = {}
    for slot in schedule.get("slots", []):
        at = dt.datetime.fromisoformat(slot["at"])
        if not (now <= at <= horizon):
            continue
        for term in _slot_terms(slot):
            if term not in out and not (canonical / term / "catalog.ndjson").is_file():
                out[term] = slot["at"]
    return out


def cmd_season_catalog(args, gh: Gh, now: Optional[dt.datetime] = None) -> int:
    schedule = load_season_schedule(args.data)
    if schedule is None:
        print(f"{args.data / SEASON_SCHEDULE_REL} 不存在（derive 沒跑？），skip")
        return 0
    now = now or dt.datetime.now(TAIPEI)
    missing = season_terms_missing_catalog(schedule, args.data / "canonical", now)
    for term, first in sorted(missing.items()):
        raise_issue(gh, season_catalog_title(term), (
            f"season 排程在 `{first}` 要刷新 `{term}` 的人數，但 data branch 沒有 "
            f"`{term}/catalog.ndjson`——season 的 enrollment 會直接失敗（要先有 catalog）。\n\n"
            f"daily 應在窗口 30 天前自動把 `{term}` 納入 catalog（D19）——這個告警代表沒生效："
            f"查最近的 daily run（該學期的 catalog 有沒有跑、是不是 0 課被 merge 丟棄）、`{term}/calendar.json` "
            f"有沒有窗口。要立即補：手動 dispatch daily 帶 `terms={term}`，或暫時把 repo var `ACTIVE_TERMS` "
            f"設成 `115-1,{term}` 這類清單（明確覆寫，事後記得清空）。步驟見 infra/README.md runbook「新學期」。"
            "學校尚未公布課程時 catalog 會是 0 課、被 merge 丟棄，屆時再等一兩天。補上（或窗口過了）自動關閉。"))
    for title in open_titles_with_prefix(gh, SEASON_CATALOG_PREFIX):
        if title[len(SEASON_CATALOG_PREFIX):] not in missing:
            resolve_issue(gh, title, "該學期已有 catalog（或窗口已過），自動關閉。")
    print(f"season-catalog: missing {sorted(missing) or 'none'}")
    return 0


def _observations(canonical: Path, term: str) -> List[dt.datetime]:
    path = canonical / term / "enrollment" / "observations.ndjson"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(dt.datetime.fromisoformat(json.loads(line)["observed_at"]))
    return out


def unmatched_season_slots(schedule: dict, canonical: Path,
                           now: dt.datetime) -> List[Tuple[str, List[str]]]:
    """[(at, [沒觀測到的學期])]：`at` ∈ [now−12h, now−1h] 且有學期沒有 [at, at+1h) 的觀測。"""
    lo, hi = now - FRESHNESS_LOOKBACK, now - FRESHNESS_GRACE
    cache: Dict[str, List[dt.datetime]] = {}
    out: List[Tuple[str, List[str]]] = []
    for slot in schedule.get("slots", []):
        at = dt.datetime.fromisoformat(slot["at"])
        if not (lo <= at <= hi):
            continue
        missed = []
        for term in _slot_terms(slot):
            obs = cache.setdefault(term, _observations(canonical, term))
            if not any(at <= o < at + OBSERVATION_TOLERANCE for o in obs):
                missed.append(term)
        if missed:
            out.append((slot["at"], missed))
    return out


def cmd_season_freshness(args, gh: Gh, now: Optional[dt.datetime] = None) -> int:
    schedule = load_season_schedule(args.data)
    if schedule is None:
        print(f"{args.data / SEASON_SCHEDULE_REL} 不存在（derive 沒跑？），skip")
        return 0
    now = now or dt.datetime.now(TAIPEI)
    missed = unmatched_season_slots(schedule, args.data / "canonical", now)
    if missed:
        lines = "\n".join(f"- `{at}`：{', '.join(terms)}" for at, terms in missed)
        raise_issue(gh, SEASON_FRESHNESS_TITLE, (
            f"檢查時間 `{now.isoformat(timespec='seconds')}`（看 {FRESHNESS_LOOKBACK.seconds // 3600} "
            f"小時內、已過 {FRESHNESS_GRACE.seconds // 3600} 小時的觸發格）。以下觸發格在 [at, at+1h) "
            f"內沒有人數觀測紀錄：\n\n{lines}\n\n排查：\n"
            "- Worker 有沒有觸發：`npx wrangler tail ntutbox-season-scheduler`\n"
            "- Worker 的 GitHub token（fine-grained、actions: write）是否過期\n"
            "- `season` workflow 最近的 run：是否失敗、或 merge 丟棄了人數快照（另見 "
            "`[pipeline] season 失敗`）\n\n最近的觸發格全部對上時自動關閉。"))
    else:
        resolve_issue(gh, SEASON_FRESHNESS_TITLE, "最近的 season 觸發格都有觀測紀錄，自動關閉。")
    print(f"season-freshness: {len(missed)} unmatched slot(s)")
    return 0


# ------------------------------------------------------------------ run summary

# ------------------------------------------------------------------ GIS 快照 updateSequence 記錄（D23、#120）

GIS_SNAPSHOT = Path(__file__).resolve().parents[1] / "crawler" / "ntut_catalog" / "reference" / "gis-rooms.json"
GIS_CAPABILITIES_URL = "https://geoserver.oga.ntut.edu.tw/ows?service=WFS&version=2.0.0&request=GetCapabilities"
_UPDATE_SEQUENCE_RE = re.compile(r'updateSequence\s*=\s*"(\d+)"')


def _is_ssl_error(e: BaseException) -> bool:
    return isinstance(e, ssl.SSLError) or (
        isinstance(e, urllib.error.URLError) and isinstance(e.reason, ssl.SSLError))


def fetch_update_sequence(url: str = GIS_CAPABILITIES_URL, timeout: float = 60,
                          urlopen=urllib.request.urlopen) -> Tuple[int, Optional[str]]:
    """GetCapabilities → (updateSequence, 備註)。學校憑證鏈 Python 驗不過（campus-map 也遇過，
    它對個別 URL 做 fallback）→ **只對這一個公開唯讀 URL** 不驗證重試一次，備註回傳給 log。"""
    note = None
    try:
        with urlopen(url, timeout=timeout) as resp:
            body = resp.read()
    except Exception as e:  # noqa: BLE001
        if not _is_ssl_error(e):
            raise
        note = f"TLS 驗證失敗（{e}），對 {url} 不驗證憑證重試一次（公開、唯讀、只讀 updateSequence）"
        with urlopen(url, timeout=timeout, context=ssl._create_unverified_context()) as resp:
            body = resp.read()
    m = _UPDATE_SEQUENCE_RE.search(body[:4096].decode("utf-8", errors="replace"))
    if m is None:
        raise ValueError("GetCapabilities 回應找不到 updateSequence")
    return int(m.group(1)), note


def gis_drift_summary(snapshot_seq, live_seq, note: Optional[str]) -> str:
    """run summary 的一段 markdown（只記錄、不開 issue；見 cmd_gis_drift）。"""
    state = "一致" if live_seq == snapshot_seq else "不同（僅記錄，不代表教室有變）"
    lines = ["### GIS 快照 updateSequence（D23）", "",
             "| repo 快照 | 線上 GeoServer | 狀態 |", "|---|---|---|",
             f"| {snapshot_seq} | {live_seq} | {state} |", "",
             "updateSequence 會因與教室無關的圖資變動前進（2026-09 三週 1044→1146，教室 0 變動），"
             "所以這裡只記錄；長期處理見 issue #120。"]
    if note:
        lines += ["", f"> {note}"]
    return "\n".join(lines) + "\n"


def cmd_gis_drift(args, gh: Optional[Gh] = None, fetch=None) -> int:
    """**只記錄、不開 issue**：線上 updateSequence 與快照寫進 run summary＋`::notice`。

    原本不相等就開 issue，但 updateSequence 會因與教室無關的變動前進（2026-09 三週 1044→1146，
    room-index.json 完全相同，只多了 21 筆建物與 2 處 sourceProperties 修改）→ 那會是每週的誤報。
    長期改由外部 repo 發佈的 GIS 資料處理（issue #120）。學校不通只發 warning。`gh` 不使用。
    """
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    snapshot_seq = (snapshot.get("source") or {}).get("update_sequence")
    fetch = fetch or fetch_update_sequence
    try:
        live_seq, note = fetch()
    except Exception as e:  # noqa: BLE001 — 學校不通只記 warning
        print(f"::warning title=GIS 漂移檢查失敗::GetCapabilities 讀取失敗，本週略過：{type(e).__name__}: {e}")
        return 0
    if note:
        print(f"::notice title=GIS 漂移檢查::{note}")
    print(f"::notice title=GIS 快照 updateSequence::repo 快照 {snapshot_seq}、線上 {live_seq}"
          f"（{'一致' if live_seq == snapshot_seq else '不同，僅記錄，見 issue #120'}）")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(gis_drift_summary(snapshot_seq, live_seq, note))
    return 0


def render_summary(stages: Optional[Path], merge_reports: Optional[Path]) -> str:
    """各資料集 fetch／merge 結果表（寫進 $GITHUB_STEP_SUMMARY；Actions 列表看不出哪個資料集
    失敗，spec §3 的對策之一）。"""
    merged: Dict[tuple, str] = {}
    partial: List[dict] = []
    for p in sorted(merge_reports.rglob("merge-report*.json")) if merge_reports and merge_reports.exists() else []:
        r = json.loads(p.read_text(encoding="utf-8"))
        for a in r.get("applied", []):
            text = "內容有變" if a.get("changed") else "已確認、未變"
            if a.get("partial"):
                text += f"；⚠️ {a.get('failed_nodes')} 個節點沿用 HEAD／缺漏"
            merged[(a["name"], a.get("term"))] = text
        for d in r.get("dropped", []):
            merged[(d["name"], d.get("term"))] = f"丟棄：{d.get('reason')}"
        partial += r.get("partial", [])
    lines = ["## 資料集", "", "| 資料集 | 學期 | fetch | merge |", "|---|---|---|---|"]
    for p in sorted(stages.rglob("pipeline-result.json")) if stages and stages.exists() else []:
        for e in json.loads(p.read_text(encoding="utf-8")).get("datasets", []):
            key = (e.get("name"), e.get("term"))
            if not e.get("ok"):
                fetch = f"❌ {e.get('error')}"
            elif e.get("failed_nodes"):
                fetch = f"⚠️ {len(e['failed_nodes'])}/{e.get('node_total')} 節點失敗"
            else:
                fetch = "✅"
            lines.append(f"| {key[0]} | {key[1] or '_global'} | {fetch} | {merged.get(key, '—')} |")
    if partial:
        lines += ["", "## 部分節點失敗（已從 HEAD 沿用）", "",
                  "| 資料集 | 學期 | 失敗 | 沿用 HEAD | HEAD 也沒有（缺漏） |", "|---|---|---|---|---|"]
        for x in partial:
            lines.append(f"| {x.get('name')} | {x.get('term') or '_global'} | "
                         f"{x.get('failed')}/{x.get('node_total')} | "
                         f"{_node_labels(x.get('carried_forward'))} | {_node_labels(x.get('missing'))} |")
    return "\n".join(lines) + "\n"


def _node_labels(nodes) -> str:
    """`[{"unit": "59"}]` → `unit=59`（與 merge.node_label 相同寫法；這裡不 import crawler）。"""
    return "、".join("/".join(f"{k}={v}" for k, v in n.items()) for n in nodes or []) or "—"


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
    r.add_argument("--web-redeploy", default="", help="commit-publish 的 web-redeploy 輸出（failed… → 告警）")
    sm = sub.add_parser("summary", help="資料集結果表 → $GITHUB_STEP_SUMMARY（不動 issue）")
    sm.add_argument("--stages", type=Path, default=None)
    sm.add_argument("--merge-reports", type=Path, default=None)
    s = sub.add_parser("stale", help="資料過期告警（讀 fetch-state）")
    s.add_argument("--data", type=Path, default=Path("data"))
    sc = sub.add_parser("season-catalog", help="season 窗口學期缺 catalog 告警（讀 ops/season-schedule.json）")
    sc.add_argument("--data", type=Path, default=Path("data"))
    sf = sub.add_parser("season-freshness", help="season 未依排程執行告警（排程 × 觀測紀錄）")
    sf.add_argument("--data", type=Path, default=Path("data"))
    gd = sub.add_parser("gis-drift", help="GIS 快照 updateSequence 記錄（只寫 run summary、不開 issue，D23／#120）")
    gd.add_argument("--snapshot", type=Path, default=GIS_SNAPSHOT)
    args = ap.parse_args(argv)
    if args.command == "summary":
        return cmd_summary(args)
    if args.command == "gis-drift":
        return cmd_gis_drift(args)
    gh = gh or default_gh()
    if args.command == "run":
        return cmd_run(args, gh)
    if args.command == "season-catalog":
        return cmd_season_catalog(args, gh)
    if args.command == "season-freshness":
        return cmd_season_freshness(args, gh)
    return cmd_stale(args, gh)


if __name__ == "__main__":
    sys.exit(main())
