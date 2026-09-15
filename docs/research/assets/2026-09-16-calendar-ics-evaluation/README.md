# 行事曆資料源評估：Google Calendar ics vs 學校 `calModeApp.do`

調查日期 2026-09-14 ~ 2026-09-16，從 NTUTBox（App）端發起。用來決定行事曆事件要不要
從學校 API 換到校網提供的 Google Calendar，以及該由 App 直抓還是本站轉 CDN。

結論寫在 **poterpan/NTUTBox#181**，這裡放的是它引用的原始資料與可重跑的腳本。

## 一句話結論

Google ics 能完整取代學校 API（共同區間 97 筆逐字完全相等，0 差異），但它沒有 ETag、
沒有 CORS、條件式 GET 無效，所以**適合由本站抓取轉 CDN，不適合 App 每次啟動直抓**。

## 檔案

| 檔案 | 內容 |
|---|---|
| `gcal-vs-school-diff.md` | 覆蓋率比對報告（2026-08-01~2027-07-31，三類差異各 0 筆），含日期語意對齊方式 |
| `gcal-vs-school-summary.json` | 上表的數字摘要 |
| `raw/gcal-basic.ics` | 2026-09-14 抓下的 ics 快照，661 筆 VEVENT，201,696 bytes。`full.ics` 內容完全相同（UID 集合與完整簽章 md5 皆相同），故不另存 |
| `raw/gcal-full-headers.txt` | ics 的完整 HTTP 回應標頭。**無 ETag／Last-Modified／ACAO**，`Cache-Control: no-store`，送 `If-Modified-Since` 回 200 全量。⚠️ 進版控前把 `set-cookie:` 的值遮掉了（匿名請求下 Google 回的 `NID` 追蹤 cookie，與任何帳號無關，但沒有保存價值、且正是公開 repo 紅線規則要擋的樣式） |
| `raw/cal-raw-threeyear.json` | 學校 API 2024-01-01~2028-12-31 全量，837 筆。**需登入才抓得到，重抓成本高，這份要留著** |
| `raw/cal-raw-app-exact-pm1y.json` | 與 App `initialFetch()` 完全相同參數（今天 ±1 年）的回應，378 筆 |
| `raw/calshow-get-id.raw` | `calShow.do?id=61722` 的回應，證明來源端存的是「結束日 = 開始日 − 1 天」 |

## 腳本

都是唯讀查詢。需要登入的會從 `NTUT_Tools/.env` 讀帳密（檔案本身不含任何憑證）。

| 腳本 | 用途 |
|---|---|
| `ics_lib.py` | ics 解析（全天 / 有時刻 / 缺 DTEND 的處理） |
| `build_report.py` | 產生 `gcal-vs-school-diff.md` |
| `compare_gcal_school.py` | 兩邊逐筆比對的核心邏輯 |
| `probe_cal.py` | 打 `calModeApp.do`，可帶任意 startDate/endDate |
| `probe_calshow.py` | 打 `calShow.do`，看單筆事件的原始欄位 |
| `compare_show_vs_list.py` | 明細端點 vs 列表端點的逐筆差異（產出兩者正規化規則的對照表） |
| `fetch_61722.py` | 撈單筆事件並印出逐欄型別與時間戳換算 |

## 兩件對發布端有直接影響的事

**1. VEVENT 的排列順序不穩定。** 同一份連抓兩次順序不同（只有 DTSTAMP 與排序變）。
**不能用檔案 md5 判斷有沒有更新**，必須正規化後比對。

**2. 這個 feed 有 horizon。** 最遠只到 2027-07-03（115 學年度結束），沒有任何 116 學年度資料。
依 `CREATED` 分群，每個批次對應一個學年度，但匯入時間 3 月到 8 月都出現過
（114 學年度提前 5 個月，112 學年度拖到開學當月且分上下學期兩批）。
判準要用 `max(DTSTART) >= 次年 6 月`，不是「有沒有新學年的事件」。

## 一個順帶發現：學校 API 的資料在來源端就是壞的

同一筆事件在兩個端點長得不一樣：

```
61722 寒假開始、寒宿開始
  calShow.do（明細）    2027/01/11 → 2027/01/10   ← 結束比開始早一天
  calModeApp.do（列表） 2027/01/11 → 2027/01/11   ← +1 天正規化後變成零長度
```

全天事件在列表端點一律 +1 天（end-exclusive），有時刻的事件則原樣不動。單日事件在
inclusive 語意下應該是 `01/11 → 01/11`，存成 `01/11 → 01/10` 是無效的。

這在 App 端造成過一次整批事件靜默消失（poterpan/NTUTBox#180，已修）。**同一批事件在
Google ics 是乾淨的標準 end-exclusive**（661 筆中零長度 0 筆），這是換源最具體的理由。

## 進版控前的個資檢查（2026-09-16）

- `python3 infra/redline_scan.py` 掃本目錄：命中 `suspect_student_id` 兩筆，**經核實全為誤判** ——
  `cal-raw-threeyear.json` 與 `cal-raw-app-exact-pm1y.json` 裡所有 9 位以上數字（共 3,398 個）**全部是 13 位 epoch 毫秒**。
- 學校 API 兩份 dump 的人員欄位全是機構帳號，不是自然人：`ownerName` = 「學校行事曆」、
  `creatorId` = `ntutoaa`、`creatorName`／`modifierName` = 「教務處」；
  `calInviteeList`／`calAlertList`／`attachment` 三個欄位 837 筆**全空**。
- 腳本從環境變數／`NTUT_Tools/.env` 讀帳密，**無任何寫死的憑證**。
- `raw/gcal-full-headers.txt` 的 `set-cookie` 值已遮罩（見上表）。

注意 `redline_scan.py` 只掃 `.json`／`.ndjson`，`.ics`／`.txt`／`.raw`／`.py` 是另外人工掃的
（cookie／session／帳密／授權標頭／9 位數學號樣式）。
