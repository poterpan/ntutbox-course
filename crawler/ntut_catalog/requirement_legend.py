"""修別符號 → 必選修類別（Cprog.jsp?format=-5 官方圖例，全域靜態）。

圖例（live 實證 2026-06-14）：
  ○ 必 部訂共同必修 / △ 必 校訂共同必修 / ☆ 選 共同選修
  ● 必 部訂專業必修 / ▲ 必 校訂專業必修 / ★ 選 專業選修
→ 符號→類別是全域固定，毋需逐課查課程標準即可定 required/elective。
通識(general)/學程(program) 等更細分類由其他訊號（pool kind/notes）補。
"""
from __future__ import annotations

from typing import Optional

from models import Requirement, RequirementCategory

# symbol → (category, 詳細必選修類別)
_LEGEND = {
    "○": (RequirementCategory.required, "部訂共同必修"),
    "△": (RequirementCategory.required, "校訂共同必修"),
    "☆": (RequirementCategory.elective, "共同選修"),
    "●": (RequirementCategory.required, "部訂專業必修"),
    "▲": (RequirementCategory.required, "校訂專業必修"),
    "★": (RequirementCategory.elective, "專業選修"),
}


def build_requirement(symbol: Optional[str]) -> Requirement:
    if symbol and symbol in _LEGEND:
        cat, label = _LEGEND[symbol]
        return Requirement(symbol=symbol, category=cat, label_zh=label)
    return Requirement(symbol=symbol, category=RequirementCategory.unknown)
