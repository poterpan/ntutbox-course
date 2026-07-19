# 北科課程查詢系統（課程目錄）調查 — 為「排課系統」鋪路

> 調查日期：2026-06-12。目的：在做「選課系統」之前，先做一個**排課系統**（讓使用者在選課開放前先排好課表、建立志願清單），
> 需先把**課程目錄（catalog）資料來源**摸透。本文不涉及「選課動作」本身（cwish/oads/新生選課見 [`NTUT_Tools 私有 PoC repo 的 course_selection_systems.md`](./NTUT_Tools 私有 PoC repo 的 course_selection_systems.md)）。

## 0. 一句話結論

- **我們之前沒有做過課程目錄爬蟲。** 現有 `ntut/nportal/course.py` 抓的是「**登入後個人課表**」(RWD / Select.jsp)，需要登入，**不是**全校開課目錄。
- **資料來源用「舊版」`/course/tw/`，不要用「新版」`/course/mobile/`。** 新版只是換皮，後端同一支 `QueryCourse.jsp`，且**欄位更少、沒有結構化連結**，學校自己標註「僅供參考」。
- **要、而且一定要把資料快取到我們自己的伺服器/資料集**（跟學長一樣）。原始 JSP 慢、有限流、不能即時逐人查；排課需要「全目錄、可搜尋、可離線」的乾淨 JSON。
- **戰略加分點**：排課系統的產出（志願清單、優先序）可以**直接餵進我們已經做好的 cwish/oads 搶課自動化** → 我們能做到學長做不到的「排課 → 搶課」閉環。

---

## 1. 學校的課程查詢系統長怎樣

公開、**免登入**的課程查詢系統，host：`https://aps.ntut.edu.tw/course/`，編碼 **UTF-8**（注意：跟 cwish 預選的 Big5 不同系統）。

有兩個前端入口，**共用同一個後端**：

| | 舊版（桌機） | 新版（手機） |
|---|---|---|
| 入口 | `/course/tw/QueryCurrPage.jsp` | `/course/mobile/QueryCurrPage.jsp` |
| 查詢 action | `POST QueryCourse.jsp` | `POST QueryCourse.jsp`（**同一支**） |
| 表單參數 | `year,sem,matric,unit,cname,ccode,tname,stime,D0–D6,P1–P13` | **完全相同** |
| `stime` 編碼 | `day*100+kk`（PN→22） | **完全相同邏輯** |
| 切換 | 右上 `view-rocker` 切換鈕，只是把網址 `/tw/` ↔ `/mobile/` 互換 | 同左 |

新版**唯一**的新東西：一個可點選的「上課時間」九宮格（`schedule-table`，`setCell`/`isSelected`），但它只是去勾同一組隱藏 checkbox、算出同一個 `stime`。**沒有 JSON API、沒有 SPA、沒有新資料。**

### 1.1 新舊版回傳結果實測比較（year=114, sem=1, 資工系 unit=59, 日間部）

| | 舊版 `/course/tw/` | 新版 `/course/mobile/` |
|---|---|---|
| 表格欄位 | **24 欄**（完整） | **11 欄**（壓扁） |
| 班級/教師/教室 | `<a href=...code=XXX>` **可連結、帶代碼** | **純文字、無連結（`code=` 連結數 = 0）** |
| 每日節次 | 日/一/二/…/六 **獨立 7 欄** | 合併成「上課星期節次教室」一欄 |
| 學分/時數 | 分開兩欄 | 合併「2.0/4」 |
| 人數/撤選 | 分開兩欄 | 合併「73/0」 |
| 課綱/TA/語言/備註 | 有 | 縮減 |
| 學校自評 | — | footer 明寫：**「※ 手機板資料僅供參考，正式資料以（原課程系統電腦版）為主。」** |

> **實測數字**：同一查詢，舊版 49 KB / 285 個 `code=` 連結；新版 45 KB / **0** 個 `code=` 連結。
> 新版對「閱讀」友善，對「爬取」**更差**——它把建立關聯資料（系所↔班級↔教師↔教室）所需的代碼全拿掉了。

### 1.2 舊版 `/course/tw/` 端點地圖（全部免登入、GET 除 QueryCourse 外）

| 端點 | 用途 | 關鍵參數 |
|---|---|---|
| `QueryCurrPage.jsp` | 查詢首頁，含學年/學期/學制/系所下拉 | — |
| `QueryCourse.jsp` | **主力**：開課清單（HTML 表格） | `POST` `year,sem,matric,unit,cname,ccode,tname,stime,D*,P*` |
| `Curr.jsp?format=-2&code=<課程碼>` | 課程中英文名稱＋課程描述 | `code`=課程碼(如 2B05002) |
| `ShowSyllabus.jsp?snum=<課號>&code=<教師碼>` | 教學大綱（目標/進度/評量/教材/SDGs/AI…） | 每位老師一份 |
| `Subj.jsp?format=-2&year&sem` | 系所列表 | `format=-3` 某系班級、`-4` 某班課表(`code`=班級碼) |
| `Teach.jsp?format=-3&year&sem&code=<教師碼>` | 教師課表 | |
| `Croom.jsp?format=-3&year&sem&code=<教室碼>` | 教室課表（可做空教室查詢） | |
| `SearchMProgram.jsp?format=-1&year&sem` | 微學程列表 | `format=-2&code` = 該學程課程 |
| `Cprog.jsp?format=-1` | 課程標準/畢業標準（年→學制→系所下鑽） | `-2&year` / `-3&year&matric` / `-4&...&division` |
| `Select.jsp?format=-2&code=<學號>&year&sem` | **個人**已選課表（**需登入** app SSO） | 我們的 `course.py` 用這支 |

### 1.3 重要參照資料（從 query 表單抓到，比學長硬編碼完整）

`matric`（學制）共 ~17 種組合，例：
`日間部='1','5','6','7','8','9'`、`進修部='4','A','D','C','E','F'`、`研究所='8','9','A','C','D'`、`全校='0','1','4','5','6','7','8','9','A','C','D','E','F'`（**全校＋所有系所同時查會被擋**），另有 日間部四技='7'、研究所(碩博)='8','9'、EMBA='D'、週末碩士班='C'、學程='1'… 等細分。

`unit`（開課單位/系所）完整代碼表已存於本次抓到的 `/course/mobile/QueryCurrPage.jsp` HTML：`01 教務處 / 05 進修部 / 10 體育室 / 14 通識中心 / 2B 智動科 / 30 機械 / 31 電機 / 32 化工 / 34 土木 / 36 電子 / 37 工管 / 38 工設 / 39 建築 / 54 應英 / 59 資工 / AB 資財 / AC 互動設計 …`（共 ~60+ 單位）。

`stime`（節次）編碼：`星期(0–6)*100 + 節次碼`，節次碼 1–4、**中午 N=22**、5–9、A–D（晚上）。

---

## 2. 學長專案「北科課程好朋友」拆解（gnehs，開源可參考）

兩個 repo（皆 ISC/開放授權，可 fork）：

### 2.1 爬蟲 `ntut-course-crawler-node`（Node.js）
- **打的就是上面 `/course/tw/` 那組端點**（免登入）。`axios` + `cheerio` + `cheerio-tableparser`(處理 colspan)。
- 限流自保：每頁 `delay 100–600ms` + 失敗指數退避重試（學長說課程網抓太快會被封；**抓 20 年資料花了約兩天**）。
- 流程：`fetchYearSem`(學年學期清單) → `fetchDepartment`(系所/班級) → `fetchCourse`(QueryCourse 開課清單 + 逐課 `Curr.jsp` 補中英描述) → `fetchSyllabus`(逐課 `ShowSyllabus`) → `fetchMProgram`(微學程) → `fetchStandards`(畢業標準) → `fetchCalendar`(Google Calendar ical 校曆)。
- **產物存成靜態 JSON**，GitHub Actions **每日** cron 跑、push 到 `gh-pages` 分支。
- 開課清單 table 解析（live 實測 24 欄）：`td[0]`課號 `td[1]`課名 `td[2]`階段 `td[3]`學分 `td[4]`時數 `td[5]`修別符號 `td[6]`班級(連結) `td[7]`教師(連結) `td[8..14]`日~六節次 `td[15]`教室(連結) `td[16]`人數 `td[17]`撤選 `td[18]`**授課語言**(非 TA！) `td[19]`課綱連結 `td[20]`備註 `td[21]`隨班附讀 `td[22]`實驗實習 `td[23]`跨領域(inline 微學程名)。
  - ⚠️ **gnehs 欄位索引 bug**（盤點實證）：它把 `td[18]` 當 TA、又把 `language` 硬編成 `""`，導致其資料 **language 永遠空、ta 永遠 []**（110-1/114-1 皆驗證）。→ **我們解析務必以表頭文字定位欄位、不要寫死索引**；欄數≠24 整列告警進 `rawFields`。授課語言(EMI)其實來源就有、且有用（資工 62 列中英語 13/中英雙語 1）。

### 2.2 資料集（`gh-pages` 分支 = `https://gnehs.github.io/ntut-course-crawler-node`）
- 結構：`/{學年}/{學期}/main.json`(日間部) `/進修部.json` `/研究所(...).json` `/department.json` `/mprogram.json` `/course/{課號}.json`(課綱) ＋ 頂層 `main.json`(年期索引) `standards.json` `/{年}/standard.json` `calendar.json` `analytics/withdrawal*.json`(退選率)。
- **涵蓋 82～115 學年（20+ 年）**，**每日更新**（最後更新 2026-06-12）。115/1（2026 秋）課程尚未公布（只有 standard.json）。
- 單一學期 `main.json` ≈ 2539 課 / 數 MB。

**每課 JSON 形狀（已驗證）**：
```jsonc
{
  "id": "346719", "code": "2B05003",          // id=課號(全系統主鍵)，code=課程碼(對標準)
  "name": {"zh":"人工智慧","en":"..."},
  "description": {"zh":"...","en":"..."},
  "courseType": "▲",                          // ○△☆●▲★ = 課程標準/必選修符號
  "credit": "3.0", "hours": "3", "stage": "1",
  "class":     [{"name":"智動五","code":"2652","link":"Subj.jsp?...code=2652"}],
  "teacher":   [{"name":"莊政達","code":"...","link":"Teach.jsp?...code=..."}],
  "time":      {"sun":[],"mon":["3","4"],"tue":[],"wed":[],"thu":[],"fri":["4"],"sat":[]},
  "classroom": [{"name":"六教526","code":"438","link":"Croom.jsp?...code=438"}],
  "people": "24", "peopleWithdraw": "0",      // 容量 / 撤選數（爬取當下快照，會過期）
  "language": "", "ta": [], "notes": "",      // notes 兼當標籤(博雅/創創…)
  "courseDescriptionLink": "Curr.jsp?format=-2&code=2B05003",
  "syllabusLinks": ["ShowSyllabus.jsp?snum=346719&code=..."]
}
```
- **節次模型（重要、非直覺）**：不是 1–14，而是 `1,2,3,4,N,5,6,7,8,9,A,B,C,D`（中午 N、晚上 A–D），各對應牆鐘時間（slot1=08:10…）。
- `time` 為「每日 → 節次字串陣列」；很多研究所/專題課全空。

### 2.3 網站 `ntut-course-web`（Nuxt2 / Vue2 靜態 SPA）
- **無後端**，直接 fetch 上面 gh-pages 的 JSON（base URL 在 `nuxt.config.js`）。大 JSON 用 **pako gzip + IndexedDB(localforage) + TTL** 快取。
- 功能：課程搜尋（支援 regex、依課程標準符號/博雅/時間篩選）、**我的課程＝排課**（週課表 grid、衝堂偵測）、課綱、退選率排行、微學程、畢業標準、空教室查詢、校曆、**匯出 .ics**、**iOS Scriptable widget 產生器**。
- **排課狀態**：純 `localStorage`（`my-couse-data-{year}-{sem}` 存課號陣列），無帳號、無雲端同步 → app 本身警告「資料只在瀏覽器、可能消失」。
- **衝堂偵測**：就是兩課 `time[day]` 節次字串陣列**取交集**（O(n²) 小集合）。**不考慮**單雙週、半學期、分組 → 我們的排課可以做得更細。
- **可直接借用**：JSON schema、節次↔時間對照表、.ics 匯出邏輯、衝堂原語。

---

## 3. 我們現有的相關資產

- `ntut/nportal/course.py`：`get_rwd_schedule()`（`aps-rwd.ntut.edu.tw/RWDCourse`，需登入）、`get_full_schedule()`（`Select.jsp`，需 app SSO）→ **都是個人課表，非目錄**。
- `ntut/nportal/models.py`：已有 `Course` / `CourseDetail`（`schedule: Dict[str,List[int]]`，與學長 `time` 模型相近，可對齊）。
- **選課自動化已完成**（見 `NTUT_Tools 私有 PoC repo 的 course_selection_systems.md`）：cwish 期末預選（加/退/多選/外班，批次 POST、優先序＝陣列順序、學分上限即時擋）；oads 加退選（偵測開放期、選課確認）。
- 慣例：`models.py` 加 dataclass → 新建服務 class（繼承 `NTUTBaseClient`）→ `ntut/tools.py` 整合 → `tests/`。（見 [[project-nature]]）

---

## 4. 決策與建議

### 4.1 用新版還是舊版？→ **舊版 `/course/tw/`**
1. 同一後端，新版零資料優勢；
2. 舊版有 `code=` 連結（系所/班級/教師/教室關聯）、每日節次分欄、課綱/人數/撤選——**爬取所需的結構全在舊版**；
3. 學校官方標註新版「僅供參考」。
4. 新版**只**值得當「我們自己 UI 九宮格選時段」的視覺參考，與資料來源無關。

### 4.2 需不需要快取到自己的伺服器？→ **需要**
- 原始 JSP 慢、有限流、「全校＋所有系所」被擋 → 全目錄要按 `學制×系所` 分頁打數千次、耗時數小時，**不可能逐使用者即時查**。
- 目錄在學期內近乎靜態（只有人數/撤選會動）→ **每日批次刷新**即足夠。
- 排課需要「全目錄、可搜尋、可離線、跨平台」→ 只有預先建好的乾淨 JSON 能滿足；client（iOS/Web）也不該自己去解 JSP（CORS/編碼/限流/解析）。
- 這正是學長快取的原因，我們照做。

### 4.3 託管架構（定案：GitHub Actions + Cloudflare）

把工作拆成「**運算（跑爬蟲）**」與「**出口（放 JSON）**」兩件事，各放最適合的平台：

```
NTUT /course/tw/           GitHub Actions (cron)            git repo (資料)            Cloudflare              iOS / Web
QueryCourse.jsp 等   ──►   Python 爬蟲 → 乾淨 JSON   ──►   commit (保留歷史)   ──push──►  R2 / Pages   ──CDN──►  讀 JSON / SQLite
                           公開 repo 無限分鐘、長 job OK                        egress $0、邊緣快取、自訂網域
```

- **爬蟲跑在 GitHub Actions**：公開 repo **無限分鐘**、單 job 最長 6hr、cron 方便、Node/Python 環境齊全。**不要**用 Cloudflare Workers 跑爬蟲（單次 50 子請求 + CPU 上限，爬不動）。
- **管線排程（三 workflow 共用 `data-pipeline` concurrency 序列化，不撞 data branch / R2）**：`crawl.yml` **每日** 04:00（台北）爬當前學期 catalog/enrollment/微學程；**`crawl-details.yml` 每週日** 05:30（台北）爬課綱詳情（~5k 請求/學期、學期內變動慢 → 週更即足夠，`--include-details` 一併發佈 R2）；`crawl-enrollment.yml` 選課季人數輕量刷新。每日與週更管線都在 commit 前跑 `pua-scan`（`continue-on-error`）**監測新造字**：canonical 出現 `PUA_MAP` 未收錄的 PUA（unicode category `Co`）碼位即 fail-loud 提醒考證（處置照 `docs/research/2026-07-20-pua-glyph-verification.md` 的 GServer 流程補 `PUA_MAP`），但不阻斷 commit/publish。
- **資料 commit 進 git**：免費紅利＝**選課人數時間序列**（commit 歷史就是 enrollment 快照，學長的退選率分析即源於此）。
- **對外出口走 Cloudflare**（R2 物件儲存或 Pages 靜態）：**egress 永遠 $0**、邊緣快取、自訂網域、可自控 cache header；同一個 Action 結束時用 `wrangler` 推上去。避開 GitHub Pages 100GB/月軟上限與「拿 Pages 當 API」的 ToS 灰色地帶。
- **免費額度速記**：GH Actions 公開 repo 無限；Cloudflare Pages 頻寬無限／500 builds 月；R2 10GB 儲存、讀 1000 萬次/月、egress $0。
- **App 端省頻寬鐵律**（不論放哪都要做）：按學期切檔（別塞 20 年）、gzip/brotli、`ETag` 條件式請求（沒變回 304）、裝置端快取＋TTL。一個學期 `main.json` 就 **5MB**，這條決定免費額度撐多久。
- **開發期 bootstrap**：先直接讀學長 gh-pages JSON（CORS 全開、即用）把排課 UX 做出來；正式版換成我們自己的爬蟲＋Cloudflare 出口（schema 設計見 §4.5，刻意做到能無痛切換資料源）。
  - iOS 端用 SwiftData/Core Data 存「每學期志願課號陣列」，並提供 **iCloud 同步**（解掉學長「資料只在瀏覽器、可能消失」痛點）。

### 4.4 我們的獨特價值：排課 → 搶課 閉環
學長的網站是**唯讀查詢/排課**工具，到「排好課」為止。我們已經有 cwish/oads 搶課自動化：
- 排課系統產出的**優先序志願清單**可直接對應 cwish **單一批次 POST 的 subj 陣列順序**（最想要的放前面，學分上限即時擋）；
- → 「開窗前排好 → 開窗瞬間自動送出最佳志願」是我們能做、別人沒做的差異化。
（搶課時序/並發/一機二機策略細節見 `NTUT_Tools 私有 PoC repo 的 course_selection_systems.md` §1。）

### 4.5 發佈格式與查詢引擎（定案：Web v1）+ Schema

**結論：不沿用學長 JSON，設計 typed v1 自有格式；Web v1 走純靜態 JSON + 前端索引，canonical 保留 NDJSON，SQLite 延後給 iOS/進階版。**
學長的形狀已被舊版表格驗證過、資料量小（每學期數 MB，適合靜態託管），但弱型別、`link` 字串、中文檔名、缺 metadata、enrollment 陳舊——不該變成長期合約。

**對學長 schema 的具體改進**：
1. **型別化**：`credit/hours/stage/people/peopleWithdraw` 由 string → number/int；原始字串只留在 `rawFields`(debug)。`people` 語意分清：`enrolledCount`(已選) 與 `capacity`(上限) 分欄、皆 nullable。
2. **丟掉 `link`、只留 `code`**：`Subj.jsp?...code=2652` 是爬蟲實作細節、且把 client 綁死在學校 JSP 路徑；URL 模板放 metadata 即可。
3. **`courseType` 符號語意化但保留原符號**：`requirement.symbol="▲"` ＋ `requirement.category`(required/elective/general/...)；category 等爬到課程標準頁再對映，先別猜。
4. **加 envelope/metadata**：每個檔含 `schemaVersion / term / generatedAt / crawlStartedAt / crawlFinishedAt / sourceSystem / 爬蟲 gitSha`——CDN 會 aggressive cache，metadata 讓 client 偵測格式變更與陳舊。
5. **避免中文檔名**：改 ASCII（`day/extension/graduate`）或乾脆不按學制切檔，把學制當課程欄位；中文檔名對 URL/CI/iOS 下載碼/未來公開 API 都是地雷。
6. **明確建模身分**：`offeringId`=課號(每學期實例、cwish `subj` 候選) vs `courseCode`=課程碼(跨學期課程身分、對描述/標準/同課多班分組)；主鍵＝`termKey + offeringId`。
7. **enrollment 與目錄分離**：最新人數放 `enrollment/latest.json`、歷史壓成 `enrollment/snapshots/YYYY-MM-DD.ndjson`(append-only) commit 進 git；每筆帶 `observedAt`，UI 顯示陳舊警告；**搶課時以 cwish 即時 addable 狀態為準、勿信靜態人數**。

**格式選擇（定案，web-first）**：
- **Canonical 來源**：**normalized NDJSON**（一行一課，commit 進 git）——可 diff、可審查、可重建 artifacts；commit 歷史＝免費 enrollment 時序。
- **Web v1 發佈／查詢引擎**：**靜態 JSON artifacts + 前端搜尋索引（FlexSearch/Orama，CJK 用 bigram tokenizer）+ Service Worker 快取**。零後端、零登入、離線 PWA。
  - 排除 **(b) Worker+D1**：不登入/不即時/公開資料 → 後端不划算（留作日後 catalog 暴增或 search-as-a-service 的後路）。
  - 排除 **(a) SQLite-WASM**：對 ~5000 筆是殺雞牛刀、WASM+DB 比精簡 JSON 還重、Safari/iOS OPFS 歷來雷、trigram 搜不到 1–2 字中文。
- **iOS / 進階版**：由**同一份 canonical** 產 `catalog.sqlite`（GRDB+FTS5）走離線；**v1 不發佈 SQLite**。各 client 共用同一包 JSON、本地自選索引即可，不必共用查詢 runtime。
- **中文搜尋**：bigram（JS 端）優於 SQLite trigram——trigram 規定 query ≥3 字、搜不到「林」「計概」；量小（~5000）時 `search_blob + includes` 子字串掃描即 sub-ms，索引庫只為排序/UX。FTS/查詢的使用者輸入務必 escape。
- **Protobuf/MessagePack**：**現在不要**——gzip JSON 已夠小，二進位對 Python/Swift/Web/debug/公開 API 都是摩擦。

**PUA（私用區）字元正規化（分層：canonical 忠實 / v1 best-effort）**：學校資料含瀏覽器無字型可畫的 PUA 字元三類——
① Word 符號字型殘留（U+F0xx，老師從 Word 貼課綱，Symbol/Wingdings 字元被存成 `0xF000+charcode`，多是條列項目符號）；
② 學校造字（U+E0xx–E2xx，教師名/課名/備註，逐字考證困難）；③ Adobe/PDF 殘留（U+F3xx/F6xx/F7xx）。
**canonical 一律保留來源原文**（忠實、可審查、可重建）；**只有 v1 消費層在 `build_v1` 時套 `ntut_catalog/pua.py` 的 `normalize_pua`**——
對照表 `PUA_MAP` 只收「能在權威字碼表核實」的碼位（Wingdings→Unicode 採 Alan Wood's Unicode Resources；Symbol 為 Adobe 標準），
**未收錄的碼位一律原樣保留（不猜、不刪）**。目前對照表：9 個 Word 符號（●■□◆•➢✓☑ 與算式內的 ±）＋ 42 個學校造字
（GServer 字形認定，部分經使用者考證覆核）。**造字字形可經學校 GServer 外字服務（`font.ntut.edu.tw` 的 `MingGaiji.TTE`）半自動考證**，
協定、認字方法與已認定清單見 `docs/research/2026-07-20-pua-glyph-verification.md`（6 個既有系網考證與 GServer 字形完全吻合＝權威反證；
近似字如 凃/涂、苷/昔、晣/晰 需上下文與外部佐證覆核；`U+EF0D` 無字形、證據未定，不入表）。分層好處：不需重爬，下次 publish 重建 v1 即修正全歷史學期；造字考證可持續補 `PUA_MAP`。
`manifest` 的 `dataset_version` = `catalog.json` sha256，會因正規化改變（屬預期：內容確實變乾淨了），非正規化學期不受影響。

**建議檔案佈局（v1）**：
```
/v1/manifest.json                       # 學期清單 + 每檔 sha256/size/datasetVersion/url
/v1/terms/114-2/catalog.json            # 主目錄（typed，web v1 主檔，前端建索引）
/v1/terms/114-2/classes.json            # 系所/年級/班級 → 班級碼（Web 身分選擇器 + 本班判斷用）
/v1/terms/114-2/periods.json            # 節次↔牆鐘時間↔排序↔顯示label（Asia/Taipei）
/v1/terms/114-2/mprograms.json          # 微學程(v2)：開課 offering_ids + 分類課程 + 規則原文
/v1/terms/114-2/course/{offeringId}.json # 重文字(描述/課綱)，隨點隨取
/v1/terms/114-2/enrollment.json         # 人數,小,選課季常更新(volatile overlay)
/v1/terms/114-2/enrollment/snapshots/2026-06-13.ndjson  # 歷史時序(git)
# catalog.sqlite 延後：iOS/進階版由 canonical 產，web v1 不發佈
```

**微學程 artifact（`mprograms.json` v2）**：
- `mprograms.json` v2（SCHEMA_VERSION=2）：每學程除 `offering_ids` 外新增
  `courses[]`（course_code/name_zh/credits/category(基礎|核心|總整|進階|應用|null)/category_raw/online，
  來源 Cprog -4 matric=H，notes 欄正規化；`online`＝notes 含 e 注記＝**線上課程**（ewant 平台，不走選課系統，
  catalog 11 學期查無開班；2026-07-19 經教務處 AVF 課程規劃書＋創新學院微學程清單確證，**非 EMI**）→
  詳情頁顯示「線上課程」標記，取代誤導的未開課灰態）與 `rules_text`（「相關規定」原文，保留換行不解析）。

**為「排課＋搶課」情境，schema 還需要學長沒有的欄位**：
- **正規化 `meetings[]`**：`{day, periods[], classroomCodes[], weekPattern(all/odd/even), dateRange, group}`——比扁平 `time{day:[...]}` 多了單雙週/半學期/分組/教室關聯（排課衝堂要這些才準）。
- **`periods.json`**：節次 token (`1-9,N,A-D`)→牆鐘起訖、排序、label、時區；排課 grid 渲染與 `.ics` 匯出必需。
- **cwish 動作鍵**：`selection.cwishSubj`(通常＝offeringId、待對驗) ＋候選/已驗 `cunum`(班級碼)；讓 App 直接從目錄組 cwish 批次 payload。
- **即時 addable overlay**：靜態目錄無法知道使用者個人可選性/gate；App 送出前要 join cwish 即時 `PreSelectCourse`(`subj/selectable/status/credit_min,max/notice/rejected`)。
- **志願清單 model**（App 端 GRDB、非目錄）：rank / 備選分組 / must-have / 上次 dry-run / 上次送出結果——直接對映 cwish「優先序 subj 陣列」送出邏輯。
- **同課多班分組**（by `courseCode`）：把多個 section 當備選呈現、避免重複排到同課。
- **學期校曆**：學期起訖/假日/特殊調課——`.ics` 匯出與排程用（可由 `Cprog`/校曆來源補）。

> Codex 完整意見（型別草案 TS interface 等）已併入上述；與 Claude 評估高度一致。差異僅在強調點：Codex 額外強調 `rawFields` 保留原始字串供 parser debug、以及搶課務必以即時狀態覆蓋靜態人數。

### 4.6 排課 → App 選課計畫 handoff（資料合約）+ 階段分類（本班/外班）

依據《北科盒子排課系統技術文件 v0.1》：**選課階段分類是 P0**；Web 排課完成後，匯出一份**已按階段分組**的選課計畫 payload，經 Universal Link / URL Scheme 導入 App，App 才負責登入與送件。Web 不送件、不登入、不碰帳密。

**階段分類機制（本班 vs 外班）— 這是效率的關鍵**：
- **權威判斷在 App、用「課號」join，不靠跨系統班級碼比對**（2026-06-13 讀碼釐清）：cwish `enter()` 已回 `cunum`(本人本班班級碼) + **本班清單**(`list_addable`) + **外班清單**(`list_addable_external`)，每課帶 `course_id`(課號)/`subj`。**課號是 cwish 與 catalog 的共用鍵**（兩邊都用 `ShowSyllabus?snum=課號`、cwish `subj==課號`，已交叉佐證；高信心，待開窗時做一次 live 端對端驗證）。→ App 送出前只需以**課號**比對 planned 課程在不在 cwish live 本班/外班清單。**不需比對 catalog 班級碼 vs cwish `cunum`（兩者實為同命名空間，送件權威走 live 清單，此比對非必要）。**
- **Web 分類＝可選的「規劃提示」、非送件必需**：Web 無登入、看不到 live 清單。要在排課當下顯示階段提示(技術文件 Table 17/P0)，就用 **catalog 自身命名空間**自洽判斷（使用者從 `classes.json` 選自己的班 → 比對課程 catalog 班級碼）；App 送件時以 live 清單為準覆蓋。可接受延後則 Web 完全不分類。→ `payload.studentContext.classCode` 降為**選用**。
- **Web 端（無登入、盡力而為）**：使用者先選「系所/年級/班級」（從 `classes.json` 取得，存 localStorage），即可分類，毋需登入：
  - 學生班級碼 ∈ 課程班級碼 → `preselection`（本班，cwish 期末初選可送）
  - 不在 → 預設 `add_drop`（外班，開學後 oads 加退選）
  - 衝堂/超學分等 → `planning_only`（僅規劃）
  - 無班級資訊 / 班級欄位解析失敗 → `unknown`（**標未知、不亂猜**，技術文件 P0 明訂）
- **⚠️ 用班級「碼」比對、不要用顯示名稱**：catalog 每課帶班級碼（如 2652／智動五），名稱格式易歧義；`classes.json` 做 名稱↔碼 對照，payload 的 `studentContext` 帶**班級碼**（+名稱供顯示）。
- **⚠️ `openClass` 要是「陣列」**：一門課可開給多個班級；分類＝學生班級碼 ∈ 該陣列（技術文件單一 `openClass?` 字串需擴成陣列）。
- **App 端權威分類（live cwish 清單，我們已实测）**：cwish 期末初選**除本班外、另允許一份限定「外班清單」**（live 才知道，已有 `get_external_classes`/`list_addable_external`）。App 以**課號**比對 planned 課程：
  - 把落在 cwish 即時「本班＋外班清單」內的課 → 歸 `preselection`；其餘外班 → 留 `add_drop`。
  - **效率效果**：絕不把「不在清單內的外班」送進 cwish——這正是我們实测會被回 `※不是本班課程※` 的情形；事前分流＝少送註定失敗的請求、降低 server try-and-error 與負載（呼應你的需求與技術文件「避免高頻 retry」）。
  - 送出順序：`preselection` 內依 `priority` 排序＝cwish 單一批次 POST 的 `subj` 陣列順序（实测：放前面的先選入、超學分擋後面）。

**選課階段/範圍的官方規則（114-2 期末預選公告，2026-06-13 使用者提供，authoritative）**：分類**不是單純本班/外班二元**，至少四種機制——
- **cwish 期末預選（6/8–6/19）**：
  - *本班直接選*：本班課程 ＋ **同系較低年級選修課程** ＋ 大三專業職場英文銜接(走外班路徑)。
  - ***志願選填(分發制)***：**博雅、體育(含專科四年級)、共同英文**——不是直接加選，是**填志願由系統分發**；共同英文以**學年**分班分發(上學期填、下學期不再填)。→ 排課器要支援志願排序；App executor 對志願課送出邏輯**異於**一般加選。
  - *外班加選*：專業職場英文銜接計畫(加選外班路徑)。
- **oads 開學加退選**：創新創業、國際觀培養、臺北聯大跨校通識博雅/全英語、**大學部三四年級體育選修**、自主學習、跨域專題。
- **獨立登記(非選課系統)**：微學程/學程「登記修讀」(教務處表單，115-1：6/8–6/22、9/7–9/18)、輔系/雙主修——**微學程不是『加課』動作**(程式內的課照常加，但加入學程是另一套登記)。
- → 分類類別應從 {preselection/add_drop/planning_only/unknown} 擴出 **`preference_ballot`(志願選填)** 並標記 **`program_registration`(獨立登記)**；技術文件 Table 8 已預示(博雅志願、英文分班)。

**cunum/subj 配對行為實證（2026-06-13 live、自身測試帳號、6 個實驗皆已回滾至 0 門）**：cwish 後端**嚴格雙層驗證 (cunum, subj)**——

| 送出 (cunum, subj) | 結果 | 訊息 |
|---|---|---|
| (本班碼, 本班課) | ✅ 選入 | 加選成功（positive control，證明 harness 真能加） |
| (授權外班碼A, 該外班課·額滿) | ❌ | 選課人數已達上限(45)（配對合法但額滿） |
| (本班碼, 外班課) | ❌ | ※不是本班課程※ |
| (授權外班碼B, 本班課) | ❌ | ※不是本班課程※（cunum 合法但非此課所屬） |
| (亂填碼9999, 本班課) | ❌ | 無法辨識的開課班級資料 |
| (別班碼·非授權, 該班課) | ❌ | 無法辨識的開課班級資料 |

- **結論1（cunum 綁本人授權）**：cunum 必須在**本人授權範圍內**（本人本班 ＋ 本人授權外班清單）；任何別班碼(他系班)或亂碼一律 `無法辨識的開課班級資料`——**預選階段無法靠填別班 cunum 搶別班課**（與官方「預選限本班＋志願＋授權外班」一致；別班/跨系得等 oads）。
- **結論2（subj 必屬該 cunum）**：cunum 合法後，subj 仍須**確實屬於該 cunum**，否則 `※不是本班課程※`。
- **→ 送件鐵則（坐實「排課來的一坨課要分班處理」）**：扁平志願清單**必須依課程所屬班級分組、各帶正確 cunum 送出**（本班課用本班碼、授權外班課用該外班碼）；**不能全部塞同一個 cunum**（結論2 已證會被擋）。每課需存 `(cwishCunum, cwishSubj)`，cunum 來源＝cwish **live 本班/外班清單**（靜態 catalog 無法知道本人授權範圍）。
- **錯誤→原因對照表（直接餵 App「錯誤訊息翻譯器」，技術文件 Table 7/16）**：`※不是本班課程※`→班級碼與課不符或非你可選範圍；`選課人數已達上限(N)`→額滿(候補/替代)；`無法辨識的開課班級資料`→cunum 非你授權(別班，留到加退選)；`請於加退選期限內辦理加選`→本班課但預選不開放(論文等)。

**Handoff payload（採技術文件 §9 + 我們的修正）**：
```jsonc
{
  "version": 1, "school": "ntut", "semester": "115-1",
  "datasetVersion": "2026-06-13T01:30Z",        // 對應 catalog 版本；App 發現過舊→提示重驗
  "source": "ntutbox-planner-web", "createdAt": "...",
  "studentContext": {                            // 供 App 重新檢查；不含帳密
    "unitCode": "59", "grade": 2,
    "classCode": "2652", "className": "資工二甲"   // 用碼比對為主、名稱供顯示
  },
  "plans": [                                     // 已按階段分組，App 不需重猜送件順序
    { "phase": "preselection", "system": "cwish",
      "courses": [ { "offeringId": "346719", "action": "add", "priority": 1 } ] },
    { "phase": "add_drop", "system": "oads",
      "courses": [ { "offeringId": "362xxx", "action": "add", "reason": "external_class" } ] },
    { "phase": "planning_only",
      "courses": [ { "offeringId": "350112", "action": "keep", "reason": "time_conflict" } ] }
  ],
  "warnings": [ { "level": "warning", "type": "phase_limited", "offeringId": "362xxx",
                  "message": "此課非本班課程，建議開學後加退選再處理。" } ]
}
```
- `offeringId` = 課號（＋`semester` 才唯一）；payload **只帶 id 不帶課程內容**，App 用自己的 catalog 還原細節。
- URL：`ntutbox://planner/import?payload=<base64url>`（Universal Link 優先、URL Scheme fallback）；太長改 server short-token。
- App 匯入後顯示確認頁（將送/不送/有警告），**送件前再以 live 重驗一次**，靜態 catalog 只做探索與規劃。

**catalog 為此要保證的欄位**：每課 `classes:[{code,name}]`（開課班級，分類用）＋ `classes.json`（系所/年級/班級↔碼，Web 身分選擇器用）。這些舊版 `/course/tw/` 都有（班級帶 `code=` 連結），已驗證。

---

## 4.7 架構差異盤點結論（vs gnehs，Fable 5 sub-agent live 實證 2026-06-13）

**已驗證、可放心的點**：
- **課號為共用鍵 = 確認**：3 檔 3,727 課**全部** `syllabusLinks` 的 `snum == id`（0 例外）、課號皆 6 位數字無重複 → §4.6 join-by-課號 成立。
- **班級碼 == cwish `cunum`（同命名空間）、但逐年跳動**（2026-06-13 用使用者實例**修正先前誤判**）：以實機帳號比對，同一研究所學位學程班級的 catalog 班級碼與 cwish `cunum` **相符**（先前誤判為不同，是拿不同班級互比所致）。班級碼與課號一樣 **per-year 重編**（同一班級不同學年碼不同）。→ `classes.json` 必**逐學期**產；catalog 班級碼可**預填** cwish `cunum`；但送件權威仍走 live 清單（志願選填/外班/額滿非碼比對能決定）。研究所/學位學程/EMBA **單一碼不分年級**，只有大學部分「年級+甲乙」。
- **單一 catalog + 學制欄位 決策正確**：gnehs 按學制切檔造成 **main∩研究所 607 筆、進修∩研究所 211 筆完全重複列**。

**來源根本沒有的資訊（雙方都拿不到，schema 別假裝有）**：
- **單雙週/半學期**：全 2,539 課結構化欄位 0 命中（僅 5 筆出現在敘述文字）→ `meetings.weekPattern/dateRange` 改 **optional、預設每週**，文件註明「來源限制、非我方未實作」；衝堂引擎只用 `day×period 交集`，不假裝更高精度。
- **教室↔星期的對應**：QueryCourse 列內教室是並排 `<a>`、與星期**無對應**（如 346719 一(3,4)+五(4) 配「六教526/726」無法對位）→ `classroomCodes` 放**課程層級**或標 nullable，要 meeting 級需另爬 `Croom.jsp`。
- **容量上限 capacity**：目錄只有「已選人數+撤選數」，**沒有上限**→ catalog 端 `capacity` 恆 null，只有 cwish live 訊息（「選課人數已達上限(45)」）能補。
- **班週會/導師時間**：不在 QueryCourse、只在各班課表頁（`Subj.jsp?format=-4`）→ v1 排課 grid 看不見每班被週會佔走的時段；v1.1 再爬 ~246 班級頁做 `classes.json.blockedSlots`。

**分類的隱藏地雷（§4.6 要補）— 「池班級」與「佔位課」**：
- 博雅掛「博雅課程(一)~(十五)」、體育掛「體育專項(一)~」、英文掛「大一/大二英文(一)~」等 **pool 班級碼**，學生班級碼永遠不在其中 → naive 本班/外班會把 **~12% 目錄**（213 博雅+67 體育+~40 英文）誤判。
- 另有 ×271 筆「請選…」**佔位課**（人數0、無教師教室，如 347440），指向 pool。
- → `classes.json` 需加 `kind: regular|pool|virtual`；分類規則加分支「課程班級為 pool → 交給 cwish live 外班清單裁決、Web 標 `pool_course` 而非 unknown」；課程加推導欄 `isPlaceholder`（notes 以「請選」開頭或 credit=0+無教師）。

**解析防呆**：表頭文字定位欄位（拒用索引，gnehs 已被咬）；`<a>` 缺失→null 不回退（gnehs `fetchCourseDescription(undefined)` 會 fallback 到寫死 `code=1400037` 接錯課）；html5lib 容錯（來源是未閉合 `<td>` 的 tag soup）；notes 結構化抽取（向度/請選目標/學號尾數分組/人數上限）但**永遠保留原文**（單字元 notes 別學 gnehs 丟棄）。

**schema 補強清單**：① `language`(EMI，enum+raw)；② 24 欄全收（`interdisciplinary`/`labCourse`/`auditAllowed` 哪怕先進 rawFields）；③ 課程標準 v1 至少存 `courseCode → {requirement.category, stageTotal, groupId}`（來源 `Cprog format=-4` 的 td[3] 課程編碼有、gnehs 漏抓）；④ `isPlaceholder` 推導欄；⑤ credit 用 decimal（有 0.5×33、0.0×214 佔位）、學分加總排除佔位課。

**bootstrap 直讀 gnehs 期間專屬**：先按課號**去重**（607+211 跨檔重複）；名稱比對先 **pangu 空白 normalize**（gnehs「實務專題 (二)」≠ 原始「實務專題(二)」），主鍵一律走課號；接受 29% 課無課綱（742/2539 無 syllabusLinks）→ detail 檔可空。

**本文件勘誤（已修）**：§2.1 `td[18]` 由「TA」更正為「授課語言」並註記 gnehs 雙空 bug；備註欄會混入教室類別文字（346719 的 `notes` 實際值是「一般教室」）。

---

## 5. 待辦 / 未解（之後回來做）

- [x] ~~決定資料託管~~ → **定案：GitHub Actions 跑爬蟲 + Cloudflare(R2/Pages) 出口 + git 留歷史**（§4.3）。
- [x] ~~資料格式方向~~ → **定案：typed v1 自有 JSON（非沿用學長）；Web v1＝靜態 JSON + 前端 bigram 索引 + SW 快取、無登入/無後端/無 SQLite-WASM；canonical＝NDJSON；SQLite 延後給 iOS/進階版**（§4.5）。
- [x] ~~handoff / 階段分類~~ → **定案：payload 按階段分組（採技術文件 §9）；Web 用班級碼盡力分本班/外班、App 用 live cwish 清單精修**（§4.6）。
- [ ] 把 §4.5/§4.6 的 schema 落成 JSON Schema / Pydantic models（與 `models.py` 對齊）；`openClass`→班級碼陣列。
- [ ] 移植爬蟲到 Python（與本專案技術棧一致）或保留 Node 爬蟲只接 schema。
- [ ] 產 `classes.json`（**逐學期**；系所/年級/班級↔碼 + `kind: regular|pool|virtual`；研究所單一碼不分年級）供 Web 身分選擇器；班級碼可預填 cwish `cunum`（同命名空間，已實機證實）。
- [ ] 分類擴成多機制：`preselection`(本班直接) / `preference_ballot`(志願選填:博雅/體育/共同英文) / `add_drop`(oads:創新創業/國際觀/跨校/三四年級體育/自主學習/跨域專題) / `program_registration`(微學程/學程/輔系/雙主修,非選課系統) / `planning_only` / `unknown`。排課器支援志願排序。
- [ ] 解析器以**表頭文字定位欄位**（非索引）；補抓 `language`(EMI)、24 欄全收、`isPlaceholder` 推導；`<a>` 缺失不回退預設。
- [ ] `meetings.weekPattern/dateRange` 設 optional（來源無）；`capacity` 標恆 null（僅 cwish live 補）；衝堂只用 day×period 交集。
- [ ] 課程標準補抓 `Cprog format=-4` 的 td[3] 課程編碼 → 建 `courseCode → requirement.category` 對照。
- [ ] (v1.1) 爬各班課表頁取 `blockedSlots`（班週會/導師時間，QueryCourse 看不到）。
- [ ] `Croom.jsp`（空教室）、`Cprog.jsp`（畢業標準/校曆）是否納入排課 MVP。
- [ ] 確認 115/1（2026 秋）開課資料公布時間（搶課排程要對上）。
- [x] ~~驗證 cunum/subj 配對行為~~ → **已 live 實證(§4.6)：後端嚴格驗 (cunum,subj)、cunum 綁本人授權、subj 必屬該 cunum；送件必依班級分組帶正確 cunum**。
- [ ] App 送件層：每課存 `(cwishCunum, cwishSubj)`，cunum 取自 cwish live 本班/外班清單，依 cunum 分組批次送；實作錯誤翻譯表(§4.6)。
- [ ] 排課狀態 model（多份草稿課表 / 每時段備選），比學長單一扁平 ID 清單更強。
- [ ] 與使用者調查的「他校好用排課系統」痛點對齊後，再定 UI 規格（使用者自行調查中）。
