"""`_meta/fetch-state.json`：每個 (資料集, 學期) 的來源新鮮度（spec §1 fetch 規則）。

```json
{ "schema_version": 1,
  "datasets": {
    "catalog":  { "115-1":   { "checked_at": "…+08:00", "changed_at": "…+08:00", "content_sha256": "…" } },
    "calendar": { "_global": { … } } } }
```

  checked_at      最後一次成功向來源確認
  changed_at      內容最後一次改變（content_sha256 變了才前進）
  content_sha256  該資料集該學期「內容檔」的合併 hash

canonical 本身不帶任何爬取時間（上游沒變 → 位元組相同 → R2 ETag 跳過、App 拿得到 304）；
「什麼時候確認過、什麼時候變過」只記在這一份。**只由上鎖的 merge 更新**，對最新 data
branch 計算——fetch job 的 checkout 可能已過期，在那裡判斷「有沒有變」會算錯。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, Optional

SCHEMA_VERSION = 1
RELPATH = Path("_meta") / "fetch-state.json"
GLOBAL = "_global"                       # 無學期維度的資料集（calendar、standards）

FetchState = Dict[str, object]


def path_for(canonical: Path) -> Path:
    return canonical / RELPATH


def empty() -> FetchState:
    return {"schema_version": SCHEMA_VERSION, "datasets": {}}


def load(path: Path) -> FetchState:
    if not path.exists():
        return empty()
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("schema_version", SCHEMA_VERSION)
    state.setdefault("datasets", {})
    return state


def save(path: Path, state: FetchState) -> None:
    """鍵排序＋縮排：每次 run 的 diff 只落在真的動到的那幾行。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                    encoding="utf-8")


def _key(term: Optional[str]) -> str:
    return term if term else GLOBAL


def get(state: FetchState, dataset: str, term: Optional[str]) -> Optional[Dict[str, str]]:
    return state.get("datasets", {}).get(dataset, {}).get(_key(term))


def _later(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if a is None:
        return b
    if b is None:
        return a
    return a if dt.datetime.fromisoformat(a) >= dt.datetime.fromisoformat(b) else b


def update(state: FetchState, dataset: str, term: Optional[str], content_sha256: str,
           checked_at: str, changed_at: Optional[str] = None) -> bool:
    """就地更新一個 (dataset, term)。回傳內容是否改變（content_sha256 不同）。

    - `checked_at` 取新舊較晚者：過期 checkout 的 run 較晚進鎖時，不可把時間往回撥。
    - hash 不變 → 只動 `checked_at`；變了 → `changed_at` 前進到 `changed_at`
      （未給就用本次的 `checked_at`）。所以兩個 run 帶著同一份新內容先後進鎖，
      第二個看到的 hash 已相同，`changed_at` 只前進一次。
    """
    entries = state.setdefault("datasets", {}).setdefault(dataset, {})
    key = _key(term)
    prev = entries.get(key)
    if prev is None or prev.get("content_sha256") != content_sha256:
        entries[key] = {
            "checked_at": _later(prev.get("checked_at") if prev else None, checked_at),
            "changed_at": changed_at or checked_at,
            "content_sha256": content_sha256,
        }
        return True
    prev["checked_at"] = _later(prev.get("checked_at"), checked_at)
    if changed_at is not None:
        prev["changed_at"] = _later(prev.get("changed_at"), changed_at)
    return False


def content_hash(paths: Iterable[Path], root: Path) -> str:
    """一組內容檔的合併 sha256：依相對路徑排序，路徑與內容都算進去（檔案增減也算改變）。"""
    h = hashlib.sha256()
    for p in sorted(paths, key=lambda x: x.relative_to(root).as_posix()):
        h.update(p.relative_to(root).as_posix().encode("utf-8") + b"\0")
        h.update(hashlib.sha256(p.read_bytes()).hexdigest().encode("ascii") + b"\n")
    return h.hexdigest()
