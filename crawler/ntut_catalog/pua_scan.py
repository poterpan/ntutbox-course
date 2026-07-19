"""新造字（PUA）碼位監測 —— canonical 出現 PUA_MAP 未收錄的碼位就 fail-loud。

背景：學校資料含私用區(PUA, unicode category `Co`)造字（教師名/課名/備註/課綱）。已考證者
收進 `pua.PUA_MAP`、v1 消費層轉真字（見 pua.py）；未來學校可能新增造字碼位，若無人發現，
web 端就會出現畫不出的 tofu。本掃描接在每日 crawl / 每週 crawl-details 管線後 fail-loud 提醒。

處置流程（發現新碼位時）：照 docs/research/2026-07-20-pua-glyph-verification.md 的 GServer
外字服務流程考證字形，補進 `pua.PUA_MAP`；若無字形/證據未定，加進 KNOWN_EXCEPTIONS 並註明。
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from ntut_catalog.pua import PUA_MAP

# 已知但刻意不收錄 PUA_MAP 的碼位（不視為「新碼位」，但也不會被 normalize 轉字）。
# EF0D：GServer 造字庫無字形輪廓、證據未定的壞損孤例，已考證不收
#       （docs/research/2026-07-20-pua-glyph-verification.md §4.2）。
KNOWN_EXCEPTIONS: frozenset[int] = frozenset({0xEF0D})

# 掃描的 canonical 檔（存在才掃）。catalog/details 為 NDJSON、mprograms 為單一 JSON。
_SCAN_FILES = ("catalog.ndjson", "details.ndjson", "mprograms.json")

_PUA_MIN = 0xE000  # 所有 category==Co 碼位皆 >= U+E000（BMP PUA 起點）→ 便宜的前置過濾


@dataclass
class PuaHit:
    """一個新 PUA 碼位的首次出現（同碼位只報一次）。"""
    codepoint: int
    field: str    # 出現位置，如 115-1/details.ndjson:syllabi[0].assessment
    context: str  # 命中字元周邊片段（≤20 字）


def _is_known(cp: int) -> bool:
    return cp in PUA_MAP or cp in KNOWN_EXCEPTIONS


def _context(text: str, idx: int, width: int = 20) -> str:
    """回傳以 idx 為中心、長度 ≤ width 的片段。"""
    half = width // 2
    return text[max(0, idx - half): idx + (width - half)]


def _walk_strings(obj, path: str, on_str) -> None:
    """遞迴走訪 dict/list，對每個字串呼叫 on_str(字串, JSON 路徑)。"""
    if isinstance(obj, str):
        on_str(obj, path)
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            _walk_strings(x, f"{path}[{i}]", on_str)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _walk_strings(v, f"{path}.{k}" if path else str(k), on_str)


def _scan_obj(obj, source: str, seen: Dict[int, PuaHit]) -> None:
    def on_str(s: str, path: str) -> None:
        for idx, ch in enumerate(s):
            cp = ord(ch)
            if cp < _PUA_MIN or cp in seen or _is_known(cp):
                continue
            if unicodedata.category(ch) == "Co":
                seen[cp] = PuaHit(cp, f"{source}:{path}", _context(s, idx))

    _walk_strings(obj, "", on_str)


def _scan_file(fpath: Path, source: str, seen: Dict[int, PuaHit]) -> None:
    text = fpath.read_text(encoding="utf-8")
    if fpath.suffix == ".ndjson":
        for line in text.splitlines():
            if line.strip():
                _scan_obj(json.loads(line), source, seen)
    else:
        _scan_obj(json.loads(text), source, seen)


def scan_canonical(out_dir: Path, terms: List[str]) -> List[PuaHit]:
    """掃指定 terms 的 canonical，回傳未收錄的 PUA 碼位命中（每碼位首次出現，依碼位排序）。"""
    base = Path(out_dir) / "canonical"
    seen: Dict[int, PuaHit] = {}
    for term in terms:
        tdir = base / term
        if not tdir.is_dir():
            continue
        for fname in _SCAN_FILES:
            fpath = tdir / fname
            if fpath.exists():
                _scan_file(fpath, f"{term}/{fname}", seen)
    return [seen[cp] for cp in sorted(seen)]


def format_report(hits: List[PuaHit]) -> str:
    lines = [
        f"pua-scan: {len(hits)} new PUA codepoint(s) — 照 "
        "docs/research/2026-07-20-pua-glyph-verification.md 的 GServer 流程考證後補 PUA_MAP："
    ]
    for h in hits:
        lines.append(f"  U+{h.codepoint:04X}  {h.field}  {h.context!r}")
    return "\n".join(lines)
