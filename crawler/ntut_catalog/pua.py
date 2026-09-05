"""PUA（私用區）字元正規化 —— **只在 v1 消費層做，canonical 保留來源原文**。

背景（2026-07-19 診斷）：學校資料含瀏覽器無字型可畫的 PUA 字元，三類：
  1. Word 符號字型殘留（U+F0xx）：老師從 Word 貼課綱，Symbol/Wingdings 字元被存成
     PUA（Word 把 symbol-font 字碼存為 0xF000 + charcode）。全出現在 details 的 syllabi。
  2. 學校造字（U+E000–E2FF，67 碼位）：教師名/notes/課名。字形一律取自學校 GServer
     外字服務（MingGaiji.TTE）認定，未取得字形者一律保留原樣。
  3. 字型子集殘留（U+F300–F8FF，以及 E 區 E300 以上）：PDF/Word 內嵌子集字型會把任意
     字形塞進任意 PUA 槽位（實測同一區出現拉丁字母 ø、成對引號、漢字），無可靠對照表
     可查 → 不處理、保留原樣。GServer 對這些碼位一律無字形輪廓，可作為判別依據。

原則：**只映射能在權威字碼表／學校字形檔核實的碼位；表中沒有的原樣保留（不猜、不刪）**。
例外：已核實為純裝飾的 Wingdings 圖示（放大鏡/太陽/花飾）映射為空字串＝刪除——
「不刪」是指不刪未考證的字，已考證確定無語意的裝飾符號刪掉才是正確結果。
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
    # ── (1b) Word 符號字型殘留（2026-09 補 22 碼；字形取自系統 Wingdings.ttf 實際輪廓）──
    # 實地佐證（非查表推測）：學校 ShowSyllabus 頁面把這些字元寫成 HTML 數值參照。
    # 「研究方法」(snum=298920) 第 8 週原文為
    #   「圖書館資源分享：&#61569;圖書館學術資源…；&#61570;美加地區碩博士論文…」
    # &#61569;=U+F081、&#61570;=U+F082，而 Wingdings 0x81/0x82 的 post 字形名正是
    # onesans/twosans（＝①②）；本批 F081–F08A 恰為連續十碼，與 Wingdings ①–⑩ 完全吻合。
    # 另「計算流體力學」(snum=298129) 課程進度以 &#61548;(U+F06C) 起條列，與既有 0xF06C=● 一致。
    #
    # 純裝飾圖示（放大鏡/太陽/裝飾引號/花飾）在課綱裡不帶語意，映射為 **空字串＝刪除**
    # 或空格；此為使用者逐碼判讀後的決定，見 issue #43 討論串。
    # 注意 U+1F56E（Unicode 7.0 對 Wingdings 0x26 的官方對應）實測無字型覆蓋、
    # 畫出來仍是空白，故 0xF026 改用覆蓋完整的 U+1F4D6 📖。
    0xF020: " ",   # Wingdings 0x20 = space；本來就是空白字元
    0xF024: "",    # Wingdings 0x24 = readingglasses（放大鏡）；純裝飾 → 刪除
    0xF026: "\U0001F4D6",  # Wingdings 0x26 = book；用於「章名↔參考文獻」分隔，保留語意 → 📖
    0xF052: " ",   # Wingdings 0x52 = sunshine（太陽）；條列裝飾 → 空格
    0xF070: " ",   # Wingdings 0x70 = box4（空心方框）；條列裝飾 → 空格
    0xF071: " ",   # Wingdings 0x71 = boxshadowdwn（陰影方框）；條列裝飾 → 空格
    0xF07E: " ",   # Wingdings 0x7E = quotedblrtbld（裝飾引號）；當條列分隔用 → 空格
    0xF081: "\u2460",  # Wingdings 0x81 = onesans   → ① CIRCLED DIGIT ONE
    0xF082: "\u2461",  # Wingdings 0x82 = twosans   → ②
    0xF083: "\u2462",  # Wingdings 0x83 = threesans → ③
    0xF084: "\u2463",  # Wingdings 0x84 = foursans  → ④
    0xF085: "\u2464",  # Wingdings 0x85 = fivesans  → ⑤
    0xF086: "\u2465",  # Wingdings 0x86 = sixsans   → ⑥
    0xF087: "\u2466",  # Wingdings 0x87 = sevensans → ⑦
    0xF088: "\u2467",  # Wingdings 0x88 = eightsans → ⑧
    0xF089: "\u2468",  # Wingdings 0x89 = ninesans  → ⑨
    0xF08A: "\u2469",  # Wingdings 0x8A = tensans   → ⑩
    0xF09E: "\u25CF",  # Wingdings 0x9E = circle2 → ● BLACK CIRCLE（與既有 0xF06C 同義）
    0xF0A2: "\u25CB",  # Wingdings 0xA2 = ring4   → ○ WHITE CIRCLE
    0xF0A7: "\u25AA",  # Wingdings 0xA7 = square4 → ▪ BLACK SMALL SQUARE
    0xF0B2: "",    # Wingdings 0xB2 = cuspopen（花飾）；純裝飾 → 刪除
    0xF0E0: "\u2794",  # Wingdings 0xE0 = barb2right → ➔ HEAVY WIDE-HEADED RIGHTWARDS ARROW
    # ── (2) 學校造字（字形認定，非猜測） ──
    # 全 45 個 PUA 造字碼位字形已由學校 GServer 外字服務（MingGaiji.TTE）採收認字，
    # 認字方法、協定與逐碼出處見 docs/research/2026-07-20-pua-glyph-verification.md。
    # 6 個既有系網考證與 GServer 字形完全吻合＝權威反證；U+ 以 ord() 計、保留異體字。
    # EF0D（無字形、證據未定）不入表，維持「未收錄一律原樣保留（不猜、不刪）」。
    0xE001: "峯",  # GServer 字形認定；楊明峯
    0xE005: "綉",  # GServer 字形認定；課綱「…門 作者： 邱聰倚, 姚家琦, 吳▨華, 黃婷琪, …」（電腦輔助製造）
    0xE00F: "琮",  # 黃琮昇（電機 ee.ntut.edu.tw/p/412-1013-16612）+ 胡琮淨（建築）兩官方頁一致；GServer 字形吻合
    0xE010: "堃",  # GServer 字形認定；課綱「…題。臺北:五南 12.陳伯璋、張盈▨編。學校教師的生…」（教師專業發展）
    0xE011: "豐",  # GServer 字形認定；課綱「…、日本豐島美術…」（課號366889）
    0xE016: "敘",  # GServer 字形為「敍」，依使用者判讀正規化為通用字「敘」；課綱「…:數據敘事的視角 - 資料類型與▨述統計 - EDA…」（金融數據分析邏輯思維）
    0xE017: "況",  # GServer 字形為「况」，依使用者判讀正規化為通用字「況」；課綱「…du.tw  台灣海洋保護區的現▨與挑戰，邵廣昭、…」（海洋環保概論）
    0xE026: "炯",  # GServer 字形認定；陳炯曉
    0xE02E: "暐",  # GServer 字形認定；課綱「…： 蘇暐婷 出…」（課號366510）
    0xE031: "凃",  # 使用者考證＋字形複驗：教材作者「凃俐雯」，左旁兩點水(冫)非三點水；採收誤認為涂（課號366510）
    0xE034: "烟",  # GServer 字形認定；課綱「… 《雲烟過眼錄…」（課號366571）
    0xE03C: "烜",  # GServer 字形認定；課綱「…人類太空與行星科學 (講師：葉永▨ (中央研究院 院…」（太空科技應用）
    0xE03F: "羣",  # GServer 字形認定；溫紹羣
    0xE041: "稜",  # GServer 字形認定；課綱「…線照進稜鏡——…」（課號362994）
    0xE043: "霙",  # GServer 字形認定；吳姉霙
    0xE046: "煒",  # 徐昕煒（工管 iem.ntut.edu.tw/p/412-1081-3754，英文名 Hsin-Wei 佐證）；GServer 字形吻合
    0xE049: "湉",  # GServer 字形認定；課綱「…、謝永湉（譯）…」（課號366781）
    0xE04D: "晧",  # GServer 字形認定；林晢晧
    0xE04F: "婕",  # GServer 字形認定；課綱「…榮 郭婕 (2…」（課號366876）
    0xE053: "珺",  # GServer 字形認定＋外部佐證：Fiske 等《傳播及文化研究主要概念》遠流譯者楊祖珺；課綱「…（楊祖珺譯），台北：遠流。」（課號366826）
    0xE054: "栢",  # GServer 字形認定；課綱「…教師李栢浡,C…」（課號325372）
    0xE055: "葳",  # GServer 字形認定；課綱「…與吳南葳老師(…」（課號361268）
    0xE058: "媜",  # GServer 字形認定＋外部佐證：簡媜《誰在銀閃閃的地方，等你》(印刻)；字形右旁 貞(⺊+貝) 非 真；課綱「…簡媜《誰在銀閃閃的地方 等你》…」（課號360744）
    0xE05F: "瀞",  # GServer 字形認定；課綱「…力.影響力.即興力.連結力﹥ 洪▨，自己的力學:找到…」（領導概論）
    0xE062: "献",  # GServer 字形認定；課綱「…王▨彰. (2020), 工廠管理,…」（工廠管理）
    0xE065: "鋒",  # GServer 字形認定；課綱「… 曾釋鋒 教授…」（課號361491）
    0xE06E: "玎",  # GServer 字形認定；課綱「… 廖凰玎，20…」（課號364509）
    0xE077: "姵",  # GServer 字形認定；課綱「…曄、丁姵如,法…」（課號325274）
    0xE07C: "銹",  # GServer 字形認定；課綱「…2.不銹鋼料（…」（課號361713）
    0xE081: "庄",  # GServer 字形認定；課綱「…生活與變遷：《頂下郊拚》<一、八甲▨的英雄們>、<八…」（文化專題（一））
    0xE082: "芃",  # GServer 字形認定；課綱「…教師蘇芃竹,社…」（課號325285）
    0xE08F: "双",  # GServer 字形認定；課綱「…. 楊双子，《…」（課號366823）
    0xE098: "瑢",  # GServer 字形認定；課綱「… 余芊瑢, 朱…」（課號366810）
    0xE0AF: "溫",  # GServer 字形認定；溫紹羣
    0xE0B2: "勳",  # 吳建勳（車輛）+ 陳佳勳（光電 eo.ntut.edu.tw/p/412-1069-12881）兩官方頁一致；GServer 字形吻合
    0xE0BF: "參",  # GServer 字形認定；課綱「…、上課參與、作…」（課號362429）
    0xE0CD: "坂",  # GServer 字形認定；課綱「…解IoT｜物聯網的開發技術與原理，▨東大輔，碁峰 畫…」（物聯網應用概論）
    0xE0E1: "勳",  # 使用者經教師本人社群帳號確認(2026-07-20)：王柏勳；與 E0B2 同字異碼（造字重複建檔）
    0xE0E3: "烱",  # GServer 字形認定；課綱「…科書:應用力學-動力學 中譯本 溫▨亮等譯 高立圖書…」（動力學）
    0xE0E9: "酶",  # GServer 字形認定；課綱「…A複製酶連鎖反…」（課號362852）
    0xE0EA: "玨",  # GServer 字形認定；課綱「…1. 王▨，【建築識圖應用「結構施工圖、建…」（工程識圖實務）
    0xE0F1: "槺",  # GServer 字形認定；課綱「…Textbook: 黃孟▨譯:高等工程數學 華泰文化…」（工程數學(一)）
    0xE0F3: "聿",  # GServer 字形認定；課綱「…易斯·康篇（2堂） 【期中考】 貝▨銘篇（2堂） 第…」（當前建築思潮）
    0xE101: "蔻",  # GServer 字形認定；賴峓蔻
    0xE102: "免",  # GServer 字形認定；課綱「…、自體免疫疾病…」（課號360924）
    0xE10A: "肽",  # GServer 字形認定；課綱「…酸、肽鍵、蛋…」（課號362380）
    0xE10C: "胜",  # GServer 字形認定；課綱「…基酸、胜鍵、…」（課號362380）
    0xE10D: "苷",  # 使用者考證＋字形複驗：上下文「核苷酸」(生化)、字形艹+甘；採收誤認為昔（課號362380）
    0xE11A: "館",  # GServer 字形認定；課綱「…研究室分機2121,綜科▨317室。…」（電子學）
    0xE122: "憙",  # GServer 字形認定；課綱「…出版社。 2.現代教育社會學。陳奎▨主編，師大書苑 …」（教育社會學）
    0xE12F: "祐",  # GServer 字形認定；課綱「…. 姚祐霆（執…」（課號366781）
    0xE136: "禎",  # 胡貝禎（學術資源網）+ 張禎庭（通識 gec.ntut.edu.tw/p/412-1021-16409）+ 林永禎（TRIZ）三方一致；GServer 字形吻合
    0xE15C: "腳",  # GServer 字形為「脚」，依使用者判讀正規化為通用字「腳」；課綱「…職場價值與優勢，協助個人在職場不同▨色扮演中，培養受…」（職場英文溝通）
    0xE17A: "个",  # GServer 字形認定；課綱「…、由來與轉變 6 定定是十七歲的彼▨畫面 聽歌曲：故…」（本土語文(一)閩南語文）
    0xE188: "塲",  # GServer 字形認定；課綱「…，4.塲發同學…」（課號362977）
    0xE195: "熺",  # 蘇春熺（機械 me1.ntut.edu.tw/p/405-1062-84645，email such@ 佐證）；GServer 字形吻合
    0xE19C: "瑤",  # GServer 字形認定；課綱「…，大塊文化出版股份有限公司。 陳柏▨/譯，村田智明/…」（法律與生活）
    0xE19E: "庙",  # GServer 字形認定；課綱「…，線上課程學習。教學影片：婆浮屠寺▨群https:/…」（中國建築史）
    0xE1B3: "廸",  # 使用者於學校「教師授課時間表」系統反白考證（該系統用真字 U+5EF8）；GServer 字形吻合
    # 注意：系網不同頁面有將 U+E1B3 正規化為「迪」(U+8FEA) 的情形，取字形較接近造字的「廸」；兩者為同名異體。
    0xE1B7: "姉",  # GServer 字形認定；吳姉霙
    0xE1D1: "棊",  # GServer 字形認定；課綱「…礎實習 作者：廖倉祥 陳奇明 王繹▨ 出版商：台科大…」（機械基礎實習(一)）
    0xE1DA: "啓",  # GServer 字形認定；課綱「…生活的啓發. …」（課號361268）
    0xE1EB: "爲",  # GServer 字形認定；課綱「…16週爲課堂實…」（課號362202）
    0xE1EC: "腈",  # GServer 字形認定；課綱「…,嫘縈,醋酸纖維;聚酯纖維,聚丙烯▨纖維,聚乙烯纖維…」（高分子化學實驗）
    0xE1F4: "暳",  # GServer 字形認定；課綱「…】國際科技談判案例介紹 講師：蔡馨▨ 第3週 9/3…」（國際科技談判）
    0xE202: "強",  # GServer 字形認定；課綱「…通過“職場英文溝通”這門課，▨化英文單字能力，熟記字…」（職場英文溝通）
    0xE26C: "晣",  # 使用者考證：政大師資頁「羅睿晣」(chinese.nccu.edu.tw)＋字形複驗右旁折(扌+斤)非晰的木旁；採收誤認為晰
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
