"""行事曆 horizon 告警：涵蓋範圍不足下一學年度 → 開 issue；補上了 → 自動關。

**告警不阻斷發布**——feed 沒有新學年不代表現有資料壞了（poterpan/NTUTBox#181）。
判準與窗口邏輯在 crawler/ntut_catalog/calendar_events.horizon_required_through，
這支只讀 canonical/calendar/meta.json 的結果、不重算，避免兩處邏輯漂移。

用法：python infra/calendar_horizon_alert.py [data 目錄]   # 需要 gh CLI 與 GH_TOKEN
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

TITLE = "行事曆 feed horizon 不足：新學年度資料尚未匯入"

BODY = """\
校網 Google Calendar feed 的涵蓋範圍已不足一個學年度，`cdn.ntutbox.com/course/v1/calendar/events.json`
與 `terms/{{term}}/calendar.json` 都會停在目前這批資料。

- feed 最遠到：`{max_start}`
- 判準：`max(DTSTART) >= 次年 6 月`（**不是**「有沒有新學年的事件」——112 學年度的下學期
  拖到 2024-02 才進來，看到新學年不等於整學年到位）

**這不阻斷發布**，現有資料沒有壞。要做的事是等教務處把新學年度匯進那本日曆；
歷史上匯入時間落在 3 月到 8 月之間，最糟會拖到開學當月。資料一進來，這個 issue 會自動關閉。

背景：poterpan/NTUTBox#181。判準實作在 `crawler/ntut_catalog/calendar_events.py`
的 `horizon_required_through`。
"""


def _gh(args: List[str]) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout.strip()


def find_open_issue() -> Optional[str]:
    out = _gh(["issue", "list", "--state", "open", "--search", f"{TITLE} in:title",
               "--json", "number", "--jq", ".[0].number // empty"])
    return out or None


def run(data_dir: Path, gh=_gh) -> int:
    meta_path = data_dir / "canonical" / "calendar" / "meta.json"
    if not meta_path.exists():
        print("no calendar meta yet, skip")
        return 0
    horizon = json.loads(meta_path.read_text(encoding="utf-8"))["horizon"]
    ok, max_start = horizon["ok"], horizon["max_start"]
    existing = gh(["issue", "list", "--state", "open", "--search", f"{TITLE} in:title",
                   "--json", "number", "--jq", ".[0].number // empty"]) or None

    if ok:
        if existing:
            gh(["issue", "comment", existing,
                "--body", f"新學年度資料已匯入，feed 現在最遠到 `{max_start}`。自動關閉。"])
            gh(["issue", "close", existing])
            print(f"horizon 恢復，已關閉 #{existing}")
        else:
            print(f"horizon ok（最遠 {max_start}）")
        return 0

    if existing:
        print(f"horizon 告警 issue 已開著：#{existing}（feed 最遠 {max_start}）")
        return 0
    gh(["issue", "create", "--title", TITLE, "--body", BODY.format(max_start=max_start)])
    print(f"已開 horizon 告警 issue（feed 最遠 {max_start}）")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    return run(Path(argv[0]) if argv else Path("data"))


if __name__ == "__main__":
    sys.exit(main())
