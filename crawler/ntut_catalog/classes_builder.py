"""classes.json 建構：逐學期班級目錄 + kind 分類。

pool 班級（博雅/體育/英文等志願分發池）學生班級碼永不在其中，
naive 本班/外班比對會誤判 ~12% 目錄（docs/DESIGN.md §4.7）→ 必須標 kind。
分類保守：regex 沒中一律 regular，不猜。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from models import ClassDirectory, ClassKind, ClassRef

# 志願分發/特殊選課 pool 班級名稱樣式（學生班級碼永不在其中）。
# 114-1 實測：博雅課程(一)~、職博雅課程(一)~、體育專項(一)~、大二專業英文(一)~(五)、
# 專業職場英文銜接計畫。注意：應英系正規班「英文一~四/英文所」不可誤標。
_POOL_RE = re.compile(
    r"博雅課程|體育專項|體育興趣|大[一二](?:專業)?英文|共同英文|英文能力分級|專業職場英文"
)

# 大學部「系名+年級(+甲乙)」抽年級；研究所（所/碩/博/EMBA/專班/學程）單一碼不分年級
_GRADE_RE = re.compile(r"(?:[一二三四五])(?:甲|乙|丙)?$")
_GRADE_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
_NO_GRADE_RE = re.compile(r"所$|碩|博|EMBA|專班|學程|學院")


def classify_kind(name: str) -> ClassKind:
    if _POOL_RE.search(name):
        return ClassKind.pool
    return ClassKind.regular


def _grade(name: str) -> Optional[int]:
    if _NO_GRADE_RE.search(name):
        return None
    m = _GRADE_RE.search(name)
    if not m:
        return None
    return _GRADE_MAP.get(m.group(0)[0])


def build_class_directory(
    term_key: str,
    subj_classes: Dict[Tuple[str, str], List[Tuple[str, str]]],
    course_classes: List[Tuple[str, str]],
) -> ClassDirectory:
    """合併 Subj.jsp -3 清單（有 unit 歸屬）與課程列中出現的班級（pool 班常只在這）。"""
    by_code: Dict[str, ClassRef] = {}
    for (unit_code, _unit_name), classes in subj_classes.items():
        for code, name in classes:
            if code not in by_code:
                by_code[code] = ClassRef(
                    code=code, name=name, kind=classify_kind(name),
                    unit_code=unit_code, grade=_grade(name),
                )
    for code, name in course_classes:
        if code not in by_code:
            by_code[code] = ClassRef(
                code=code, name=name, kind=classify_kind(name),
                unit_code=None, grade=_grade(name),
            )
    return ClassDirectory(
        term_key=term_key,
        classes=sorted(by_code.values(), key=lambda c: c.code),
    )


def resolve_class_ref(code: str, name: str, lookup: Dict[str, ClassRef]) -> ClassRef:
    """課程內嵌班級 → 從 ClassDirectory（單一真相）查回完整 kind/unit_code/grade。

    directory 由 build_class_directory 從 subj_classes + 全部課程列班級建成，
    故正常情形下每個課程內嵌 code 都在 lookup 內；fallback 僅為防呆
    （依名稱現場分類，與 directory 同一 classify_kind，不會 drift）。
    """
    ref = lookup.get(code)
    if ref is not None:
        return ref
    return ClassRef(code=code, name=name, kind=classify_kind(name), grade=_grade(name))
