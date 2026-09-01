"""資料紅線掃描：commit canonical 前擋掉個資/機密/錯誤頁漏入（公開 repo 守則）。

擋：session/cookie/帳密/授權標頭、完整 HTML 頁、學校錯誤頁標記、疑似學號（9+ 連續數字）。
課程資料合法欄位（課號6碼、課程編碼7碼英數、教師/教室/班級碼、ISO 時間戳）不應誤判。
自由文字（課綱）另放寬兩條規則，見 scan_text 的 free_text 說明。

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


# 哪些檔算「自由文字」（課綱等人類撰寫的長文）。
_FREE_TEXT_NAMES = ("details.ndjson",)
_FREE_TEXT_DIRS = ("course",)

# 自由文字（課綱）只套用「真正對得上風險」的規則。
#
# 為什麼：紅線掃描的原始意圖（2026-06-13 設計文件 §110）是防「解析失敗時 malformed row
# 整列塞進 raw_fields，夾帶整頁 HTML 進公開 repo」。但實測：
#   catalog.ndjson  每筆都有 raw_fields（models.py:324「欄數≠24 整列入此」）→ 風險成立
#   details.ndjson  完全沒有 raw_fields（3,047 筆零命中）→ 該風險不適用
#
# 而爬取是**免登入**的公開頁面，details 不可能出現 session/cookie/授權標頭/學號。
# 那三條規則對 details 只會誤判，實績兩次：
#   suspect_student_id → 課綱的 ISBN/電話（commit 5b769f5 已跳過）
#   authorization      → 課綱英文句子 "authorization: from cryptography to..."
#                        （2026-09-01 111-2 因此白爬 57 分）
#
# 留著「永遠只會誤判」的規則比沒有規則更糟——會讓人習慣性放寬，或像這次白跑一輪。
# 故 details 只掃真實風險：整頁 HTML 漏入、學校錯誤頁被當成資料。
_FREE_TEXT_RULES = frozenset({"html_page", "error_page"})


def scan_text(text: str, free_text: bool = False) -> List[str]:
    """回傳命中的紅線名稱清單（空＝乾淨）。

    free_text=True（課綱等自由文字）只套用 _FREE_TEXT_RULES——理由見其註解。
    結構化檔（catalog/classes/mprograms）維持全部規則：那裡有 raw_fields，
    解析失敗會夾帶原始 HTML，是紅線掃描真正要防的東西。
    """
    return [
        name for name, rx in _PATTERNS
        if (not free_text or name in _FREE_TEXT_RULES) and rx.search(text)
    ]


def _is_free_text(rel: Path) -> bool:
    return rel.name in _FREE_TEXT_NAMES or any(part in _FREE_TEXT_DIRS for part in rel.parts)


def scan_paths(root: Path) -> Dict[str, List[str]]:
    """掃 root 下所有 .ndjson/.json，回傳 {相對路徑: [命中名稱]}（只含有命中的檔）。"""
    root = Path(root)
    hits: Dict[str, List[str]] = {}
    for p in sorted(root.rglob("*")):
        if p.suffix not in (".ndjson", ".json") or not p.is_file():
            continue
        rel = p.relative_to(root)
        found = scan_text(p.read_text(encoding="utf-8", errors="replace"), free_text=_is_free_text(rel))
        if found:
            hits[str(rel)] = found
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
