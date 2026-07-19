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
    # ── (2) 學校造字（字形認定，非猜測） ──
    # 全 43 個 PUA 造字碼位字形已由學校 GServer 外字服務（MingGaiji.TTE）採收認字，
    # 認字方法、協定與逐碼出處見 docs/research/2026-07-20-pua-glyph-verification.md。
    # 6 個既有系網考證與 GServer 字形完全吻合＝權威反證；U+ 以 ord() 計、保留異體字。
    # EF0D（無字形、證據未定）不入表，維持「未收錄一律原樣保留（不猜、不刪）」。
    0xE001: "峯",  # GServer 字形認定；楊明峯
    0xE00F: "琮",  # 黃琮昇（電機 ee.ntut.edu.tw/p/412-1013-16612）+ 胡琮淨（建築）兩官方頁一致；GServer 字形吻合
    0xE011: "豐",  # GServer 字形認定；課綱「…、日本豐島美術…」（課號366889）
    0xE026: "炯",  # GServer 字形認定；陳炯曉
    0xE02E: "暐",  # GServer 字形認定；課綱「…： 蘇暐婷 出…」（課號366510）
    0xE031: "凃",  # 使用者考證＋字形複驗：教材作者「凃俐雯」，左旁兩點水(冫)非三點水；採收誤認為涂（課號366510）
    0xE034: "烟",  # GServer 字形認定；課綱「… 《雲烟過眼錄…」（課號366571）
    0xE03F: "羣",  # GServer 字形認定；溫紹羣
    0xE041: "稜",  # GServer 字形認定；課綱「…線照進稜鏡——…」（課號362994）
    0xE043: "霙",  # GServer 字形認定；吳姉霙
    0xE046: "煒",  # 徐昕煒（工管 iem.ntut.edu.tw/p/412-1081-3754，英文名 Hsin-Wei 佐證）；GServer 字形吻合
    0xE049: "湉",  # GServer 字形認定；課綱「…、謝永湉（譯）…」（課號366781）
    0xE04D: "晧",  # GServer 字形認定；林晢晧
    0xE04F: "婕",  # GServer 字形認定；課綱「…榮 郭婕 (2…」（課號366876）
    0xE054: "栢",  # GServer 字形認定；課綱「…教師李栢浡,C…」（課號325372）
    0xE055: "葳",  # GServer 字形認定；課綱「…與吳南葳老師(…」（課號361268）
    0xE065: "鋒",  # GServer 字形認定；課綱「… 曾釋鋒 教授…」（課號361491）
    0xE06E: "玎",  # GServer 字形認定；課綱「… 廖凰玎，20…」（課號364509）
    0xE077: "姵",  # GServer 字形認定；課綱「…曄、丁姵如,法…」（課號325274）
    0xE07C: "銹",  # GServer 字形認定；課綱「…2.不銹鋼料（…」（課號361713）
    0xE082: "芃",  # GServer 字形認定；課綱「…教師蘇芃竹,社…」（課號325285）
    0xE08F: "双",  # GServer 字形認定；課綱「…. 楊双子，《…」（課號366823）
    0xE098: "瑢",  # GServer 字形認定；課綱「… 余芊瑢, 朱…」（課號366810）
    0xE0AF: "溫",  # GServer 字形認定；溫紹羣
    0xE0B2: "勳",  # 吳建勳（車輛）+ 陳佳勳（光電 eo.ntut.edu.tw/p/412-1069-12881）兩官方頁一致；GServer 字形吻合
    0xE0BF: "參",  # GServer 字形認定；課綱「…、上課參與、作…」（課號362429）
    0xE0E1: "勳",  # 使用者經教師本人社群帳號確認(2026-07-20)：王柏勳；與 E0B2 同字異碼（造字重複建檔）
    0xE0E9: "酶",  # GServer 字形認定；課綱「…A複製酶連鎖反…」（課號362852）
    0xE101: "蔻",  # GServer 字形認定；賴峓蔻
    0xE102: "免",  # GServer 字形認定；課綱「…、自體免疫疾病…」（課號360924）
    0xE10A: "肽",  # GServer 字形認定；課綱「…酸、肽鍵、蛋…」（課號362380）
    0xE10C: "胜",  # GServer 字形認定；課綱「…基酸、胜鍵、…」（課號362380）
    0xE10D: "苷",  # 使用者考證＋字形複驗：上下文「核苷酸」(生化)、字形艹+甘；採收誤認為昔（課號362380）
    0xE12F: "祐",  # GServer 字形認定；課綱「…. 姚祐霆（執…」（課號366781）
    0xE136: "禎",  # 胡貝禎（學術資源網）+ 張禎庭（通識 gec.ntut.edu.tw/p/412-1021-16409）+ 林永禎（TRIZ）三方一致；GServer 字形吻合
    0xE188: "塲",  # GServer 字形認定；課綱「…，4.塲發同學…」（課號362977）
    0xE195: "熺",  # 蘇春熺（機械 me1.ntut.edu.tw/p/405-1062-84645，email such@ 佐證）；GServer 字形吻合
    0xE1B3: "廸",  # 使用者於學校「教師授課時間表」系統反白考證（該系統用真字 U+5EF8）；GServer 字形吻合
    # 注意：系網不同頁面有將 U+E1B3 正規化為「迪」(U+8FEA) 的情形，取字形較接近造字的「廸」；兩者為同名異體。
    0xE1B7: "姉",  # GServer 字形認定；吳姉霙
    0xE1DA: "啓",  # GServer 字形認定；課綱「…生活的啓發. …」（課號361268）
    0xE1EB: "爲",  # GServer 字形認定；課綱「…16週爲課堂實…」（課號362202）
    0xE26C: "晰",  # GServer 字形認定；羅睿晰
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
