"""commit-publish job 的 commit 步驟：只 commit 登錄表範圍內的檔，訊息由 merge 報告產生。

  python infra/data_commit.py --repo data/canonical --cadence daily --reports DIR [--message M]

- 範圍：`registry.committable`（登錄表 `writes`／`append_only`＋fetch-state＋逐週進度報告）。
  範圍外的變動（不該出現）只印 `::warning`、不 commit——不用 `git add -A`，免得哪天
  fetcher 多寫了檔就默默進公開 repo。
- 訊息：`data(<cadence>): <datasets> <terms>`（spec §3），datasets／terms 取自 `--reports`
  目錄下全部 `merge-report*.json` 的聯集；沒有報告（republish／migrate）→ `--message`。
- 沒有 diff → 不 commit。結果寫 `$GITHUB_OUTPUT` 的 `committed=true|false`。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))
from ntut_catalog.registry import committable  # noqa: E402


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], check=check, capture_output=True,
                          text=True)


def changed_paths(repo: Path) -> List[str]:
    """工作區相對 HEAD 的全部變動（含未追蹤、刪除），逐檔列出。"""
    out = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    paths, items = [], out.split("\0")
    i = 0
    while i < len(items):
        entry = items[i]
        if not entry:
            i += 1
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in status or "C" in status:     # rename：下一個欄位是原路徑
            i += 1
            paths.append(items[i])
        i += 1
    return sorted(set(paths))


def split_scope(paths: List[str]) -> Tuple[List[str], List[str]]:
    inside = [p for p in paths if committable(p)]
    return inside, [p for p in paths if p not in inside]


def message_from_reports(cadence: str, reports_dir: Optional[Path]) -> Optional[str]:
    reports = sorted(reports_dir.rglob("merge-report*.json")) if reports_dir and reports_dir.exists() else []
    if not reports:
        return None
    datasets, terms = set(), set()
    for p in reports:
        r = json.loads(p.read_text(encoding="utf-8"))
        datasets |= set(r.get("datasets") or [])
        terms |= set(r.get("terms") or [])
    parts = [",".join(sorted(datasets)) or "none"]
    if terms:
        parts.append(",".join(sorted(terms)))
    return f"data({cadence}): " + " ".join(parts)


def _output(line: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def run(repo: Path, cadence: str, reports_dir: Optional[Path], message: Optional[str]) -> bool:
    inside, outside = split_scope(changed_paths(repo))
    for p in outside:
        print(f"::warning title=commit 範圍外的變動::{p}（不在登錄表 writes 內，未 commit）")
    if not inside:
        print("no changes in scope — nothing to commit")
        return False
    _git(repo, "add", "-A", "--", *inside)
    if _git(repo, "diff", "--cached", "--quiet", check=False).returncode == 0:
        print("no staged diff — nothing to commit")
        return False
    msg = message_from_reports(cadence, reports_dir) or message or f"data({cadence}): update"
    _git(repo, "commit", "-q", "-m", msg)
    print(f"committed {len(inside)} path(s): {msg}")
    return True


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="data_commit")
    ap.add_argument("--repo", type=Path, required=True, help="data branch checkout")
    ap.add_argument("--cadence", required=True, help="訊息的 data(<cadence>) 部分")
    ap.add_argument("--reports", type=Path, default=None, help="merge 報告所在目錄")
    ap.add_argument("--message", default=None, help="沒有 merge 報告時用的訊息")
    args = ap.parse_args(argv)
    committed = run(args.repo, args.cadence, args.reports, args.message)
    _output(f"committed={'true' if committed else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
