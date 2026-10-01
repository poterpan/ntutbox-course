# 教室課表頁（/rooms/）設計

2026-10-01。決策編號 D25。

## 目的與範圍

排課 web 的「教室」總覽：查任一間教室的**整週課表**（主），附帶輕量的「現在／下一堂」與「目前沒排課」篩選。
找空教室的完整體驗（定位、個人課表）由北科盒子 App 負責，不在本範圍。

資料只用既有 v1 產物（`terms/{t}/rooms.json`、`catalog.json`、`periods.json`），不改爬蟲、不升 schema。
誠實語意沿用 D23：slot＝「有排課」，不是「被占用」；頁面一律寫「依課表」。

## 頁面

- **`/rooms/`**：依 GIS 大樓分組列出全部教室（對不到 GIS → 「其他」），每列：名稱、代碼、容量、本週排課節數。
  頂部 client 端搜尋框＋「目前沒排課」開關（非上課節次時停用並說明）。靜態 HTML 內含全部 `<a>`。
- **`/rooms/[code]/`**：URL 用學校教室代碼（已驗證 112-1／114-2／115-1 代碼↔名稱零變動）。
  標題 full_name、容量、大樓；純展示的 `RoomWeekGrid`（一～六＋有課才顯示日，× 節次表），格內課名＋教師、連課程頁；
  同格多課全列。頂部「現在／下一堂」列；頁尾 D23 語意說明與資料檢查時間。
- **課程詳情**的教室名稱連到 `/rooms/[code]/`（該學期有該教室頁時）。
- `/browse/` 頁首加「教室課表」入口。

## 學期

教室頁跟**本學期**（`resolveTerms().current`），不是 hub 的預設學期——期中撤選截止後預設學期已切下學期，
但教室裡上的仍是本學期。本學期沒有 rooms → 退回 manifest 中有 rooms 的最新學期。頁面標出學期。
（以下稱此學期為「教室學期」。）

## 資料載入

build 期 `loadRoomsCatalog()`（`lib/hub/` 旁），退路同 `loadHubCatalog`：CDN 失敗 → repo fixtures
（`public/data/v1`，需補 115-1 `rooms.json` 與 manifest 的 rooms 項）。
產出給頁面的是精簡結構：每間教室 + slots 已對好課名／教師／課程頁連結（client 不再抓 catalog）。

## 「現在」

純函式 `roomNow(now, periods, slots)`，client 端執行（靜態 HTML 不含狀態）：
- 用 `Intl.DateTimeFormat` 以 `periods.timezone`（Asia/Taipei）取星期與時:分 → 對 `start_hm`／`end_hm` 找節次。
- 節內 → 「上課中」：標亮該格，顯示課名或「依課表沒排課」，到幾點。
- 節與節之間 → 歸下一節。其餘時間 → 不標亮，只顯示「下一堂」（往後找第一個有 slot 的節次，跨週繞回）。
- 今天欄位一律標示；每分鐘＋`visibilitychange` 重算。不讀行事曆（考試週／假期／國定假日由「依課表」語意涵蓋）。

## SEO

每頁覆寫 `alternates.canonical`（root layout 預設指 `/`，不覆寫會整批消失）；title「{full_name} 教室課表（{term}）｜北科盒子 排課」；
breadcrumb 走 HubShell／HubJsonLd。`src/app/sitemap.ts` 加 `/rooms/` 與各教室頁。edge worker 不用動。

## 重建（infra/web_redeploy.py）

現行：預設學期 catalog 有變才 POST Deploy Hook。擴大為：**預設學期 catalog 有變，或教室學期的 catalog／rooms 有變**。
教室學期的 Python 解析與 web 同語意（current → 有 rooms 的最新學期）。merge 報告 `applied[].name == "rooms"` 即 canonical rooms 有變。
已知不涵蓋：只更新 GIS 快照（derive 層）不觸發——罕見，手動重建即可。同步更新 `infra/README.md` 對照表。

## 測試與驗收

- vitest：`roomNow`（節內、下課、早於第 1 節、晚於 D、週日、跨週下一堂、同格多課、UTC→台北換算）、教室學期選擇、大樓分組、`RoomWeekGrid` 渲染。
- pytest：`web_redeploy` 新條件（只有教室學期 rooms 變／catalog 變 → 觸發；都沒變或只有人數 → 不觸發）。
- build：`out/rooms/index.html` 含全部教室連結、教室頁靜態 HTML 有課名、canonical 自指、sitemap 含教室頁（grep 驗證）。
- preview 部署截圖：索引、滿課與少課教室，桌機＋手機、深色模式。
- 文件：`docs/DECISIONS.md` D25、`docs/ARCHITECTURE.md` §7、`infra/README.md`。
