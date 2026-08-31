"""Curr.jsp（課程描述）+ ShowSyllabus.jsp（教學大綱）解析。

兩者都用「表頭/標籤文字定位」（不寫死索引、不寫死欄位順序），與目錄解析同原則。
缺欄 → None（不回退）。
"""
from __future__ import annotations

from typing import Dict, Optional

from bs4 import BeautifulSoup

from models import Syllabus

# ShowSyllabus 標籤 → Syllabus 欄位
_SYLLABUS_LABELS = {
    "課程大綱": "outline",
    "課程進度": "schedule",
    "評量方式與標準": "assessment",
    "使用教材、參考書目或其他": "materials",
    "課程諮詢管道": "consultation",
    "延伸教學與資源": "extended_resources",
    "課程對應SDGs指標": "sdgs",
    "課程是否導入AI": "ai_usage",
    "備註": "notes",
}


def _clean(text: str) -> str:
    return text.replace("　", " ").replace("\xa0", " ").strip()


def _match_label(label: str) -> Optional[str]:
    """把來源標籤對映到 Syllabus 欄位，容忍校方加的後綴。

    2026-08 實測：學校把 `<th>課程進度</th>` 改成 `<th>課程進度<BR>(1-16週)</th>`，
    原本的精確比對失效 → schedule 變 None、內容掉進 extra（線上 CDN 已實際壞掉，
    週更 cron 每次都會覆寫）。校方逐年微調標題文字是常態，所以改用前綴比對。

    只允許「已知標籤 + 括號補充」這種形式，不做模糊比對——避免把不相干的標籤誤收。
    """
    if label in _SYLLABUS_LABELS:
        return _SYLLABUS_LABELS[label]
    for known, field in _SYLLABUS_LABELS.items():
        if label.startswith(known):
            rest = label[len(known):].strip()
            # 後綴必須是空的或括號補充（全形/半形），否則視為不同欄位
            if not rest or rest[0] in "（(":
                return field
    return None


def parse_curr(html: str) -> Dict[str, Optional[str]]:
    """課程描述頁 → {course_code, name_zh, name_en, description_zh, description_en}。"""
    soup = BeautifulSoup(html, "html5lib")
    out: Dict[str, Optional[str]] = {
        "course_code": None, "name_zh": None, "name_en": None,
        "description_zh": None, "description_en": None,
    }
    # 找含「課程編碼」表頭的表
    table = None
    for t in soup.find_all("table"):
        if any("課程編碼" in th.get_text() for th in t.find_all("th")):
            table = t
            break
    if table is None:
        return out

    rows = table.find_all("tr")
    # 第一列 th 表頭 → 欄位；第二列 td 值
    headers = [_clean(th.get_text()) for th in rows[0].find_all("th")] if rows else []
    if len(rows) >= 2:
        vals = [_clean(td.get_text()) for td in rows[1].find_all("td")]
        for h, v in zip(headers, vals):
            if "課程編碼" in h:
                out["course_code"] = v
            elif "中文課程名稱" in h:
                out["name_zh"] = v
            elif "英文課程名稱" in h:
                out["name_en"] = v
    # 概述列：th 含「中文概述」/「英文概述」→ 同列 td
    for tr in rows:
        th = tr.find("th")
        td = tr.find("td")
        if not th or not td:
            continue
        label = _clean(th.get_text())
        if "中文概述" in label:
            out["description_zh"] = _clean(td.get_text())
        elif "英文概述" in label:
            out["description_en"] = _clean(td.get_text())
    return out


def parse_syllabus(html: str, teacher_code: Optional[str] = None) -> Syllabus:
    """單一教師大綱頁 → Syllabus（標籤定位；未知標籤進 extra）。"""
    soup = BeautifulSoup(html, "html5lib")
    syl = Syllabus(teacher_code=teacher_code)

    # 大綱表＝含第一格為「教師姓名」的那張（排除基本資料表）
    table = None
    for t in soup.find_all("table"):
        first_cells = [c for c in t.find_all(["th", "td"], recursive=True)]
        if first_cells and _clean(first_cells[0].get_text()) == "教師姓名":
            table = t
            break
    if table is None:
        return syl

    for tr in table.find_all("tr"):
        # 115-1 起「彈性學習(17-18週)」是嵌套的 <table class="flex-learn-table">，
        # find_all("tr") 會連它的列一起撈出來，把「類別/內容/時數(小時)/學習成果/
        # 評量比例」誤當成頂層欄位塞進 extra。只處理直屬本表的列。
        if tr.find_parent("table") is not table:
            continue
        cells = tr.find_all(["th", "td"], recursive=False)
        if len(cells) < 2:
            continue
        label = _clean(cells[0].get_text())
        value_cell = cells[1]
        ta = value_cell.find("textarea")
        value = _clean(ta.get_text()) if ta else _clean(value_cell.get_text())

        if label == "教師姓名":
            a = value_cell.find("a", href=True)
            if a:
                syl.office_hours_url = a["href"]
                a.extract()
            syl.teacher_name = _clean(value_cell.get_text())
        elif label == "Email":
            syl.email = value or None
        elif label == "最後更新時間":
            syl.updated_at = value or None
        elif (field := _match_label(label)) is not None:
            setattr(syl, field, value or None)
        elif label and label not in ("教師姓名",) and value:
            syl.extra[label] = value
    return syl
