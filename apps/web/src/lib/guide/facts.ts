/**
 * 指南頁引用的制度事實 —— 集中一處、逐條標來源，並用測試釘住。
 *
 * 規則（重要，改動前先讀）：
 * 1. **只放能在 repo 內追到來源的事實**：docs/DESIGN.md 的 live 實證、crawler 的官方圖例
 *    解析、或本站課程資料本身的統計。憑印象的制度細節一律不進這個檔。
 * 2. **不放會逐年變動的數字**：選課起訖日期、學分上下限、各類別畢業學分——這些每年公告
 *    不同，寫死在靜態頁只會過期誤導人。頁面一律導向教務處公告。
 * 3. 每個常數上方註明來源檔案與段落，讓下一個 session 能核對。
 */

export interface PeriodRow {
  token: string;
  start: string;
  end: string;
}

/**
 * 節次 ↔ 上課時間（Asia/Taipei）。
 *
 * 來源：`crawler/ntut_catalog/periods.py` 的 `_WALL_CLOCK`，其 docstring 註明
 * 「權威來源：QueryCourse.jsp 回應頁尾的官方節次表（live 抓取 2026-06-13）」，
 * 且爬蟲每次抓取都用 `parse_footer_periods()` 對照來源頁尾驗證時刻沒變。
 * 節次順序見 CLAUDE.md「關鍵事實」：`1,2,3,4,N(中午),5,6,7,8,9,A,B,C,D(晚上)`，不是 1..14。
 *
 * 這裡是靜態內容頁用的離線副本（指南頁不抓 CDN 資料）；排課器本身讀
 * 每學期的 `periods.json`（見 lib/schedule/periods.ts）。
 */
export const PERIOD_TABLE: readonly PeriodRow[] = [
  { token: "1", start: "08:10", end: "09:00" },
  { token: "2", start: "09:10", end: "10:00" },
  { token: "3", start: "10:10", end: "11:00" },
  { token: "4", start: "11:10", end: "12:00" },
  { token: "N", start: "12:10", end: "13:00" },
  { token: "5", start: "13:10", end: "14:00" },
  { token: "6", start: "14:10", end: "15:00" },
  { token: "7", start: "15:10", end: "16:00" },
  { token: "8", start: "16:10", end: "17:00" },
  { token: "9", start: "17:10", end: "18:00" },
  { token: "A", start: "18:30", end: "19:20" },
  { token: "B", start: "19:20", end: "20:10" },
  { token: "C", start: "20:20", end: "21:10" },
  { token: "D", start: "21:10", end: "22:00" },
];

export interface RequirementRow {
  symbol: string;
  kind: "必修" | "選修";
  label: string;
  /** 本站收錄的開課清單裡是否實際出現過這個符號。 */
  seenInCatalog: boolean;
}

/**
 * 修別符號圖例。
 *
 * 來源：`crawler/ntut_catalog/requirement_legend.py` 的 `_LEGEND`，docstring 註明
 * 「修別符號 → 必選修類別（Cprog.jsp?format=-5 官方圖例，全域靜態），live 實證 2026-06-14」。
 *
 * `seenInCatalog`：對本站 110-1～115-1 共 11 學期的開課清單統計，只出現
 * △ ▲ ☆ ★ 四種；○ 與 ● 在官方圖例上有、但開課清單中未見。誠實標示，不假裝全都常見。
 */
export const REQUIREMENT_LEGEND: readonly RequirementRow[] = [
  { symbol: "○", kind: "必修", label: "部訂共同必修", seenInCatalog: false },
  { symbol: "△", kind: "必修", label: "校訂共同必修", seenInCatalog: true },
  { symbol: "☆", kind: "選修", label: "共同選修", seenInCatalog: true },
  { symbol: "●", kind: "必修", label: "部訂專業必修", seenInCatalog: false },
  { symbol: "▲", kind: "必修", label: "校訂專業必修", seenInCatalog: true },
  { symbol: "★", kind: "選修", label: "專業選修", seenInCatalog: true },
];

/**
 * 博雅課程的四個向度。
 *
 * 來源：本站 115-1 課程資料中，開課班級為「博雅課程(一)～(十四)」的課程（皆由通識中心
 * 開課、皆 2 學分），其備註欄出現的向度字串只有這四種：人文與藝術、社會與法治、
 * 自然與科學、創新與創業。
 *
 * ⚠️ 這是「課程備註欄怎麼寫」的觀察，不是通識中心的官方分類定義文件。各向度的
 * 應修學分與畢業要求本站查不到，頁面上不寫，一律導向通識中心公告。
 */
export const GE_DIMENSIONS: readonly string[] = [
  "人文與藝術",
  "社會與法治",
  "自然與科學",
  "創新與創業",
];

/**
 * 微學程課程的分類。
 *
 * 來源：`crawler/models.py:384` 的 `MProgramCategory = Literal["基礎","核心","總整","進階","應用"]`
 * 與 `crawler/ntut_catalog/parse_program.py:128` 的 `_MPROG_CATEGORY_BY_PREFIX`
 * （由課程標準頁 Cprog 的備註前綴「基/核/總/進/應」正規化而來）。
 */
export const MPROGRAM_CATEGORIES: readonly string[] = [
  "基礎",
  "核心",
  "總整",
  "進階",
  "應用",
];

export interface SelectionMechanism {
  name: string;
  /** 在哪個系統／哪個窗口處理。 */
  where: string;
  /** 這個機制處理哪些課。 */
  scope: readonly string[];
  /** 排課時要注意什麼。 */
  note: string;
}

/**
 * 四種選課機制。
 *
 * 來源：docs/DESIGN.md §4.6「選課階段/範圍的官方規則（114-2 期末預選公告，
 * 2026-06-13 使用者提供，authoritative）」，以及 CLAUDE.md「關鍵事實」的
 * 選課階段分類（preselection / preference_ballot / add_drop / program_registration）。
 *
 * ⚠️ 刻意不寫日期：114-2 公告的起訖日只對那一學期成立。
 */
export const SELECTION_MECHANISMS: readonly SelectionMechanism[] = [
  {
    name: "期末網路初選",
    where: "選課系統（學期末的初選窗口）",
    scope: [
      "本班課程",
      "同系較低年級的選修課程",
      "專業職場英文銜接計畫（以外班加選路徑處理）",
    ],
    note: "送出時系統會同時驗「開課班級」與「課號」，不是本班或授權範圍內的課會直接被退。",
  },
  {
    name: "志願選填（分發制）",
    where: "期末初選期間，但走志願分發、不是直接加選",
    scope: ["博雅課程", "體育（含專科四年級）", "共同英文"],
    note: "填的是志願順序、由系統分發，不是先搶先贏；共同英文以學年分班分發（上學期填、下學期不再填）。",
  },
  {
    name: "開學後加退選",
    where: "加退選系統（開學後的加退選窗口）",
    scope: [
      "跨系、跨班修讀",
      "創新創業",
      "國際觀培養",
      "臺北聯大跨校通識博雅／全英語",
      "大學部三、四年級體育選修",
      "自主學習",
      "跨域專題",
    ],
    note: "初選選不到、或本來就只在這個階段開放的課，留到這裡處理；排課時可以先排進課表當規劃。",
  },
  {
    name: "獨立登記（不經選課系統）",
    where: "教務處的登記程序（表單／專用系統）",
    scope: ["微學程、學程的登記修讀", "輔系", "雙主修"],
    note: "登記和「加課」是兩件事：課還是要在選課系統選，登記只是把你納入該學程的修讀名單。",
  },
];

export interface SelectionError {
  message: string;
  meaning: string;
  next: string;
}

/**
 * 選課系統常見回應訊息的意思。
 *
 * 來源：docs/DESIGN.md §4.6「cunum/subj 配對行為實證（2026-06-13 live、自身測試帳號、
 * 6 個實驗皆已回滾至 0 門）」的錯誤→原因對照表。是開發者以自己的帳號實測的結果，
 * 不是校方公告的錯誤碼文件——頁面上要標明這點。
 */
export const SELECTION_ERRORS: readonly SelectionError[] = [
  {
    message: "※不是本班課程※",
    meaning: "這門課不屬於你目前這個身分可以直接選的班級範圍。",
    next: "確認是不是跨系／跨班的課；若是，留到開學後加退選再處理。",
  },
  {
    message: "選課人數已達上限",
    meaning: "配對是合法的，但這門課已經額滿。",
    next: "找同課名的其他班、或先排進課表等加退選釋出名額。",
  },
  {
    message: "無法辨識的開課班級資料",
    meaning: "送出的開課班級不在你被授權的範圍內（例如別系的班）。",
    next: "初選階段無法靠填別班代碼選別班的課；等加退選。",
  },
  {
    message: "請於加退選期限內辦理加選",
    meaning: "是本班課程，但這門課在初選階段不開放（論文之類）。",
    next: "照訊息說的，等加退選窗口再辦。",
  },
];

/**
 * 課程查詢系統來源上「根本沒有」的欄位——本站也不可能有。
 *
 * 來源：CLAUDE.md「關鍵事實」的『來源根本沒有的（schema 別假裝有）』，以及
 * docs/DESIGN.md §4.7『來源根本沒有的資訊（雙方都拿不到，schema 別假裝有）』。
 */
export const SOURCE_GAPS: readonly { what: string; why: string }[] = [
  {
    what: "單雙週、半學期課程",
    why: "開課清單沒有這個欄位，只有極少數課在敘述文字裡提到；本站的衝堂判斷只比對「星期 × 節次」是否重疊，不會更精細。",
  },
  {
    what: "哪一節在哪間教室",
    why: "查詢結果的教室是整門課並排列出，和星期節次對不起來。一門課有兩間教室時，無法從這份資料判斷哪節在哪間。",
  },
  {
    what: "人數上限（還剩幾個名額）",
    why: "公開的課程查詢只給「已選人數」和「撤選人數」，沒有上限。是否額滿只有選課系統當下才知道。",
  },
  {
    what: "班週會、導師時間",
    why: "這些時段在各班的班課表頁才看得到，不在開課清單裡，所以排課格子上不會顯示被佔用。",
  },
];
