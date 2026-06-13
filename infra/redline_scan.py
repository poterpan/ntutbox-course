"""資料紅線掃描：commit canonical 前擋掉個資/機密/錯誤頁漏入（公開 repo 守則）。

擋：session/cookie/帳密/授權標頭、完整 HTML 頁、學校錯誤頁標記、疑似學號（9+ 連續數字）。
課程資料合法欄位（課號6碼、課程編碼7碼英數、教師/教室/班級碼、ISO 時間戳）不應誤判。

用法：python infra/redline_scan.py <dir>   # 命中則 exit 1 並印違規
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List

# (名稱, regex)。保守、針對性，避免誤判課程欄位。
_PATTERNS = [
    ("session", re.compile(r"JSESSIONID|Set-Cookie|\bcookie\s*:", re.IGNORECASE)),
    ("credential", re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key)\b\s*[:=]")),
    ("authorization", re.compile(r"(?i)Authorization\s*:\s*\S")),
    ("html_page", re.compile(r"(?i)<!DOCTYPE|<html[\s>]")),
    ("error_page", re.compile(r"查詢選課資料出現錯誤")),
    ("suspect_student_id", re.compile(r"\b\d{9,}\b")),  # 課號6碼/碼短，9+ 連續數字疑似學號
]


def scan_text(text: str) -> List[str]:
    """回傳命中的紅線名稱清單（空＝乾淨）。"""
    return [name for name, rx in _PATTERNS if rx.search(text)]


def scan_paths(root: Path) -> Dict[str, List[str]]:
    """掃 root 下所有 .ndjson/.json，回傳 {相對路徑: [命中名稱]}（只含有命中的檔）。"""
    root = Path(root)
    hits: Dict[str, List[str]] = {}
    for p in sorted(root.rglob("*")):
        if p.suffix not in (".ndjson", ".json") or not p.is_file():
            continue
        found = scan_text(p.read_text(encoding="utf-8", errors="replace"))
        if found:
            hits[str(p.relative_to(root))] = found
    return hits


def main(argv: List[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    root = Path(argv[0]) if argv else Path("data/canonical")
    hits = scan_paths(root)
    if hits:
        print(f"❌ redline scan FAILED — {len(hits)} file(s) with violations under {root}:", file=sys.stderr)
        for path, names in hits.items():
            print(f"  {path}: {', '.join(names)}", file=sys.stderr)
        return 1
    print(f"✅ redline scan clean: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
