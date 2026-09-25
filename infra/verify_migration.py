"""管線 v2 遷移的離線驗證（spec §7）：舊程式碼 derive 的 v1 vs 遷移後新程式碼 derive 的 v1。

  python infra/verify_migration.py <old_v1> <new_v1> [--report PATH]

逐檔比對，**只允許**下列差異，其餘一律算不允許、exit 1：

  manifest.json             `published_at`／`generated_at`（publish 才寫入，不比）、新增每個產物項目的 `checked_at`／`changed_at`、
                            每學期的 `details`（spec §6）。產物檔本身有允許的差異時，對應項目的
                            `sha256`／`size` 跟著變，也允許。
                            catalog 的 `count` 在 PR 2 已上線，舊版也有，照比。
  terms/*/course/*.json     移除 `generated_at`、`weekly_progress.parsed_at`；`weekly_progress`
                            內容差異允許但**列報**（derive 以現行 parser 重算；舊 canonical 大多
                            學期根本沒存 progress）——每學期 status 計數前後對照。
  terms/*/enrollment.json   只允許 JSON 物件鍵的順序不同（遷移把快照列依課號排序）；
                            數字與 `observed_at` 必須相同。

其他產物（catalog／classes／periods／names／mprograms／calendar／events／standards）必須逐位元組相同。
報告為 markdown（預設印到 stdout）。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_MANIFEST_NEW_ENTRY_KEYS = ("checked_at", "changed_at")
NO_PROGRESS = "（無）"
STATUSES = ("resolved", "partial", "unparsed", NO_PROGRESS)
MAX_LISTED = 50


def artifact_type(rel: str) -> str:
    parts = rel.split("/")
    if rel == "manifest.json":
        return "manifest.json"
    if parts[0] == "terms" and len(parts) == 4 and parts[2] == "course":
        return "course/{id}.json"
    if parts[0] == "terms" and len(parts) == 3:
        return parts[2]
    if parts[0] == "standards":
        return "standards/*.json"
    if parts[0] == "calendar":
        return "calendar/" + parts[-1]
    return "其他"


def _files(root: Path) -> Dict[str, Path]:
    return {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}


def first_diff(a, b, path: str = "$") -> Optional[str]:
    """兩個 JSON 值第一個不同處的路徑（報告用）。"""
    if type(a) is not type(b):
        return f"{path}: 型別 {type(a).__name__} → {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                return f"{path}.{k}: 新增"
            if k not in b:
                return f"{path}.{k}: 移除"
            d = first_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: 長度 {len(a)} → {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else f"{path}: {a!r} → {b!r}"


def _status(wp: Optional[dict]) -> str:
    return wp.get("status", "?") if wp else NO_PROGRESS


def compare_course(old: dict, new: dict) -> Tuple[Optional[str], bool, List[Tuple[str, str]]]:
    """回傳 (不允許的差異, weekly_progress 內容是否不同, [(舊 status, 新 status)…])。"""
    old, new = dict(old), dict(new)
    old.pop("generated_at", None)
    new.pop("generated_at", None)
    so, sn = old.pop("syllabi", []) or [], new.pop("syllabi", []) or []
    bad = first_diff(old, new)
    if bad:
        return bad, False, []
    if len(so) != len(sn):
        return f"$.syllabi: 長度 {len(so)} → {len(sn)}", False, []
    wp_changed = False
    statuses = []
    for i, (a, b) in enumerate(zip(so, sn)):
        a, b = dict(a), dict(b)
        wa, wb = a.pop("weekly_progress", None), b.pop("weekly_progress", None)
        bad = first_diff(a, b, f"$.syllabi[{i}]")
        if bad:
            return bad, False, []
        if wa:
            wa = {k: v for k, v in wa.items() if k != "parsed_at"}
        if wb and "parsed_at" in wb:
            return f"$.syllabi[{i}].weekly_progress.parsed_at: 新版不該再有", False, []
        if wa != wb:
            wp_changed = True
        statuses.append((_status(wa), _status(wb)))
    return None, wp_changed, statuses


def _strip_manifest(m: dict, is_new: bool, loose_urls: set) -> dict:
    """去掉允許的欄位；`loose_urls` 內的產物（檔案本身有允許差異）連 sha256／size 一起去掉。"""
    m = json.loads(json.dumps(m))
    m.pop("generated_at", None)          # 兩者都由 publish 在上傳前寫入（derive 產出恆為 null）
    m.pop("published_at", None)

    def entry(e):
        if not isinstance(e, dict):
            return e
        if is_new:
            for k in _MANIFEST_NEW_ENTRY_KEYS:
                e.pop(k, None)
        if e.get("url") in loose_urls:
            e.pop("sha256", None)
            e.pop("size", None)
        return e

    for t in (m.get("terms") or {}).values():
        if is_new:
            t.pop("details", None)
        for k, v in list(t.items()):
            if isinstance(v, dict) and "url" in v:
                t[k] = entry(v)
        cat = t.get("catalog") or {}
        if cat.get("url") in loose_urls:
            t.pop("dataset_version", None)
    for k, v in (m.get("calendars") or {}).items():
        m["calendars"][k] = entry(v)
    return m


def verify(old_root: Path, new_root: Path) -> dict:
    old_files, new_files = _files(old_root), _files(new_root)
    per_type: Dict[str, Counter] = defaultdict(Counter)
    disallowed: List[str] = []
    loose_urls: set = set()
    wp_before: Dict[str, Counter] = defaultdict(Counter)
    wp_after: Dict[str, Counter] = defaultdict(Counter)
    wp_changed_files: Counter = Counter()

    for rel in sorted(set(old_files) - set(new_files)):
        per_type[artifact_type(rel)]["只在舊版"] += 1
        disallowed.append(f"`{rel}`：新版沒有這個檔")
    for rel in sorted(set(new_files) - set(old_files)):
        per_type[artifact_type(rel)]["只在新版"] += 1
        disallowed.append(f"`{rel}`：舊版沒有這個檔")

    for rel in sorted(set(old_files) & set(new_files)):
        if rel == "manifest.json":
            continue
        kind = artifact_type(rel)
        per_type[kind]["總數"] += 1
        ob, nb = old_files[rel].read_bytes(), new_files[rel].read_bytes()
        is_course = kind == "course/{id}.json"
        term = rel.split("/")[1] if rel.startswith("terms/") else None
        if ob == nb and not is_course:
            per_type[kind]["相同"] += 1
            continue
        if is_course:
            bad, wp_changed, statuses = compare_course(json.loads(ob), json.loads(nb))
            for before, after in statuses:
                wp_before[term][before] += 1
                wp_after[term][after] += 1
            if ob == nb:
                per_type[kind]["相同"] += 1
                continue
            if bad:
                per_type[kind]["不允許"] += 1
                disallowed.append(f"`{rel}`：{bad}")
                continue
            per_type[kind]["允許的變動"] += 1
            if wp_changed:
                per_type[kind]["其中 weekly_progress 內容不同"] += 1
                wp_changed_files[term] += 1
            continue
        if kind == "enrollment.json":
            bad = first_diff(json.loads(ob), json.loads(nb))
            if bad:
                per_type[kind]["不允許"] += 1
                disallowed.append(f"`{rel}`：{bad}")
            else:
                per_type[kind]["允許的變動（僅鍵順序）"] += 1
                loose_urls.add(rel)          # manifest 的 url 與 v1 相對路徑相同
            continue
        per_type[kind]["不允許"] += 1
        try:
            why = first_diff(json.loads(ob), json.loads(nb)) or "JSON 相同但位元組不同"
        except ValueError:
            why = "位元組不同"
        disallowed.append(f"`{rel}`：{why}")

    if "manifest.json" in old_files and "manifest.json" in new_files:
        per_type["manifest.json"]["總數"] += 1
        om = json.loads(old_files["manifest.json"].read_bytes())
        nm = json.loads(new_files["manifest.json"].read_bytes())
        bad = first_diff(_strip_manifest(om, False, loose_urls), _strip_manifest(nm, True, loose_urls))
        if bad:
            per_type["manifest.json"]["不允許"] += 1
            disallowed.append(f"`manifest.json`：{bad}")
        elif om == nm:
            per_type["manifest.json"]["相同"] += 1
        else:
            per_type["manifest.json"]["允許的變動"] += 1

    return {"ok": not disallowed, "per_type": per_type, "disallowed": disallowed,
            "wp_before": wp_before, "wp_after": wp_after, "wp_changed_files": wp_changed_files,
            "old_count": len(old_files), "new_count": len(new_files)}


def _fmt_counts(c: Counter) -> str:
    return " / ".join(str(c.get(s, 0)) for s in STATUSES)


def render(result: dict, old_root: Path, new_root: Path) -> str:
    out = ["# 管線 v2 遷移驗證報告", ""]
    out.append(f"- 舊版 v1：`{old_root}`（{result['old_count']} 檔）")
    out.append(f"- 新版 v1：`{new_root}`（{result['new_count']} 檔）")
    out.append(f"- 結論：**{'通過' if result['ok'] else '不通過'}**"
               f"（不允許的差異 {len(result['disallowed'])} 處）")
    out += ["", "## 各產物類型變動檔數", "",
            "| 產物 | 總數 | 相同 | 允許的變動 | 其中 weekly_progress 內容不同 | 不允許 | 只在一邊 |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for kind in sorted(result["per_type"]):
        c = result["per_type"][kind]
        allowed = c["允許的變動"] + c["允許的變動（僅鍵順序）"]
        note = "（僅鍵順序）" if c["允許的變動（僅鍵順序）"] else ""
        out.append(f"| `{kind}` | {c['總數']} | {c['相同']} | {allowed}{note} | "
                   f"{c['其中 weekly_progress 內容不同'] or ''} | {c['不允許']} | "
                   f"{(c['只在舊版'] + c['只在新版']) or ''} |")
    out += ["", "## weekly_progress 各學期 status（遷移前 → 遷移後）", "",
            "每格為 resolved / partial / unparsed / " + NO_PROGRESS + "（以 syllabus 計）。"
            "「遷移前」是舊 canonical 存的結果（大多數學期沒存過，全是（無））；"
            "「遷移後」是 derive 以現行 parser 即時計算。", "",
            "| 學期 | 遷移前 | 遷移後 | progress 有變的課程檔 |", "|---|---|---|---:|"]
    for term in sorted(set(result["wp_before"]) | set(result["wp_after"])):
        out.append(f"| {term} | {_fmt_counts(result['wp_before'][term])} | "
                   f"{_fmt_counts(result['wp_after'][term])} | "
                   f"{result['wp_changed_files'].get(term, 0)} |")
    out += ["", "## 不允許的差異", ""]
    if not result["disallowed"]:
        out.append("無。")
    else:
        for line in result["disallowed"][:MAX_LISTED]:
            out.append(f"- {line}")
        if len(result["disallowed"]) > MAX_LISTED:
            out.append(f"- …另有 {len(result['disallowed']) - MAX_LISTED} 處")
    return "\n".join(out) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("old_v1", type=Path)
    ap.add_argument("new_v1", type=Path)
    ap.add_argument("--report", type=Path, default=None, help="markdown 報告輸出路徑（預設 stdout）")
    args = ap.parse_args(argv)
    result = verify(args.old_v1, args.new_v1)
    text = render(result, args.old_v1, args.new_v1)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
