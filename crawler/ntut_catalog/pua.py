"""PUA（私用區）字元正規化 —— **只在 v1 消費層做，canonical 保留來源原文**。

背景（2026-07-19 診斷）：學校資料含瀏覽器無字型可畫的 PUA 字元，三類：
  1. Word 符號字型殘留（U+F0xx）：老師從 Word 貼課綱，Symbol/Wingdings 字元被存成
     PUA（Word 把 symbol-font 字碼存為 0xF000 + charcode）。全出現在 details 的 syllabi。
  2. 學校造字（U+E0xx–E2xx，~30 碼位）：教師名/notes/課名。已考證 6 碼位（見 PUA_MAP (2) 段：
     E00F琮 E046煒 E0B2勳 E136禎 E195熺 E1B3廸），其餘未考證者一律保留原樣。
  3. Adobe/PDF 殘留（U+F3xx/F6xx/F7xx）：不處理、保留原樣。

原則：**只映射能在權威字碼表核實的碼位；表中沒有的原樣保留（不猜、不刪）**。
canonical 端不套用本模組；下次 publish 重建 v1 時歷史資料一併修正（分層設計，不需重爬）。

對照表依據：
  - Symbol（Adobe）字碼：0x6C=λ 0x6E=ν 0x6F=ο 0x75=υ（皆希臘字母）
    → 這些在課綱裡當「條列項目符號」用（每個後接 \\t + 條列內容），希臘字母語意不通，
      故取 Wingdings 解讀。0xB1 例外見下。
  - Wingdings 字碼→Unicode（Unicode 7.0 收錄 Wingdings 字形；對照採 Alan Wood's
    Unicode Resources, https://www.alanwood.net/demos/wingdings.html）：
      0x6C=● 0x6E=■ 0x6F=□ 0x75=◆ 0x9F=• 0xD8=右向箭頭 0xFC=✓ 0xFE=☑
  - 目標碼位刻意挑「常見字型必有」者（Geometric Shapes / Dingbats / General Punctuation），
    避免換一個瀏覽器同樣畫不出的冷僻碼位。
"""
from __future__ import annotations

# 碼位 → 取代字。逐筆註明來源字型 + 原字形，方便日後審查/補充。
# 未考證的 E 區造字碼位一律保留原樣（不猜、不刪）；待考證清單見 issue #43。
PUA_MAP: dict[int, str] = {
    # ── (1) Word 符號字型殘留（皆課綱條列符號；Symbol 解讀為希臘字母、語意不通 → 取 Wingdings） ──
    0xF06C: "●",  # Wingdings 0x6C = ● BLACK CIRCLE（實心圓項目符號）
    0xF06E: "■",  # Wingdings 0x6E = ■ BLACK SQUARE（實心方塊項目符號）
    0xF06F: "□",  # Wingdings 0x6F = □ WHITE SQUARE（空心方塊項目符號）
    0xF075: "◆",  # Wingdings 0x75 = ◆ BLACK DIAMOND（實心菱形項目符號）
    0xF09F: "•",  # Wingdings 0x9F = • BULLET（項目符號）
    # Wingdings 0xD8 = 右向 3D 箭頭（alanwood 記 U+2B9A 等邊變體）；改用 Dingbats 區、字型覆蓋佳
    # 且為 Word 常見「箭頭項目符號」的 U+27A2，保留「右向箭頭」語意。
    0xF0D8: "➢",  # ➢ THREE-D TOP-LIGHTED RIGHTWARDS ARROWHEAD
    0xF0FC: "✓",  # Wingdings 0xFC = ✓ CHECK MARK（Word「ü→打勾」慣例；取文字呈現的 U+2713）
    0xF0FE: "☑",  # Wingdings 0xFE = ☑ BALLOT BOX WITH CHECK（alanwood 記 U+1F5F9，改用 BMP 等義字）
    # 0xB1 例外：唯一出現在「平時成績(◻10%)」的算式括號內、非條列位置。
    # Wingdings 0xB1=⌖(位置標記) 語意不通；Symbol 0xB1=± 在成績算式中合理 → 取 Symbol 解讀。
    0xF0B1: "±",  # Symbol 0xB1 = ± PLUS-MINUS SIGN
    # ── (2) 學校造字（僅收錄已逐字考證者；其餘 E 區碼位一律保留原樣） ──
    # 以下 5 筆皆教師名造字，2026-07-19 交叉比對學校各系官方師資頁考證（證據 URL 附各行）。
    0xE00F: "琮",  # 黃琮昇（電機 ee.ntut.edu.tw/p/412-1013-16612）+ 胡琮淨（建築）兩官方頁一致
    0xE046: "煒",  # 徐昕煒（工管 iem.ntut.edu.tw/p/412-1081-3754，英文名 Hsin-Wei 佐證）
    0xE0B2: "勳",  # 吳建勳（車輛）+ 陳佳勳（光電 eo.ntut.edu.tw/p/412-1069-12881）兩官方頁一致
    0xE136: "禎",  # 胡貝禎（學術資源網）+ 張禎庭（通識 gec.ntut.edu.tw/p/412-1021-16409）+ 林永禎（TRIZ）三方一致
    0xE195: "熺",  # 蘇春熺（機械 me1.ntut.edu.tw/p/405-1062-84645，email such@ 佐證）
    0xE1B3: "廸",  # 廸（2026-07-19 使用者於學校「教師授課時間表」系統反白考證，該系統用真字 U+5EF8）
    # 注意：系網不同頁面有將 U+E1B3 正規化為「迪」(U+8FEA) 的情形，取字形較接近造字的「廸」；兩者為同名異體。
}


def normalize_pua(text: str) -> str:
    """把字串中 PUA_MAP 有對照的碼位換成真字；**沒對照的原樣保留（不猜、不刪）**。"""
    if not text:
        return text
    # 無 PUA 對照字元時走快速路徑，避免無謂重建字串
    if not any(ord(ch) in PUA_MAP for ch in text):
        return text
    return "".join(PUA_MAP.get(ord(ch), ch) for ch in text)


def normalize_pua_obj(obj):
    """遞迴正規化 dict/list/str（其餘型別原樣回傳）。回傳新物件，不 mutate 輸入。

    保留為物件走訪（obj-walk）替代方案；production 寫出路徑走序列化字串層
    （artifacts._write_v1_json → normalize_pua），因本 repo 序列化不 \\u 轉義，
    對字串做碼位替換與此遞迴等價、且省一次 re-dump 的格式漂移。
    """
    if isinstance(obj, str):
        return normalize_pua(obj)
    if isinstance(obj, list):
        return [normalize_pua_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: normalize_pua_obj(v) for k, v in obj.items()}
    return obj
