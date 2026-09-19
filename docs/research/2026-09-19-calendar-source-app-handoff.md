# 發布端待辦：行事曆事件與學年度週次表（App 端接收前）

2026-09-19｜由 NTUTBox App 端發起｜對應 poterpan/NTUTBox#181、#168

## 緣由

北科盒子 App 的行事曆事件目前直接打學校的 `calModeApp.do`。那個 API 的格式會無預警改變——
2026 年起單日全天事件從 end-exclusive 變成 `calStart == calEnd`，造成 App 整批事件靜默消失
（58 筆具名事件看不到，poterpan/NTUTBox#180，已修）。同一批事件在校網提供的 Google Calendar
feed 裡是乾淨的，因此決定換源，並由本站抓取後轉 CDN。

學年度週次表（`terms/{term}/calendar.json`）原本就規劃要從 bundle 改成遠端覆寫
（poterpan/NTUTBox#168），與換源共用同一套遠端載入／快取／降級機制，所以兩件事併成 App 端的
同一個 PR 處理。

2026-09-19 對已上線的端點做了一輪逐條驗證，結論是**三塊資料大致到位，但有幾項會讓 App 端做不完
或在未來靜默失效**。本文件列出的就是那些項目。

### 已驗證通過、不需要動的部分

- 行事曆事件 feed：661 筆與來源 ics 的 VEVENT **UID 完全對齊**（缺漏 0、多出 0）；
  零長度壞資料 0 筆；`summary` 661/661 逐字保留（含行尾空格）
- `terms/115-1/calendar.json` 與 App 內建 `term-calendar-115.json` 的 115-1 **逐欄位全等**
- 欄位名與型別全部符合 App decoder 預期（`weeks[].number` 確認不叫 `index`）
- HTTP 層：ETag 存在、`If-None-Match` 實測回 304、CORS 正確、gzip 大小符合契約估計
- `weekly_progress` 的 `week` 與 `calendar.json` 的 `weeks[].number` **編號同源**，已交叉驗算

證據與可重跑的腳本：`docs/research/assets/2026-09-16-calendar-ics-evaluation/`

---

## 必修

不處理的話 App 端這輪會壞或做不完。

1. **calendar 的發布與 manifest 收錄不綁課程目錄**
   現象：`terms/115-2/calendar.json` 404。該檔已產出於 `origin/data` 且通過全部不變量，
   但 115-2 沒有課程目錄，既未上傳也未出現在 `manifest.terms`。

2. **事件 feed 的全天結束日改為 end-exclusive**
   現象：目前單日事件是 `start_date == end_date`（inclusive）。App 模型為 exclusive。
   語意不一致的失敗模式是「多日事件少掉最後一天」，不報錯、不崩。
   **App 端要等這項完成才能合併。**

3. **修掉 2027-08-01 起會讓整條管線紅燈的推導失敗**
   現象：`build_all_term_calendars` 全有全無、`cli.py:250` 無 try/except。
   新學年下學期 ics 晚到時（`calendar_events.py:55-62` 自記 112 學年度拖到 2024-02），
   步驟非零退出 → commit 與 publish 都不執行 → **行事曆事件 feed 一併停更**。

---

## 建議

4. **發布所有已產出的學期 calendar，不限當前學期**

5. **填入 manifest 的 `generated_at`**（目前為 null）

6. **新增「已發布的 calendar 涵蓋哪些學期」的驗證**
   現況：`infra/` 內無此驗證。horizon 告警只量 ics 來源的日期涵蓋範圍，
   所以此刻 `horizon.ok == true` 與 `terms/115-2/calendar.json` 404 同時成立。

7. **事件新增 `is_holiday` 欄位**（新功能，可延後）
   現況：事件只有 11 個欄位，國定假日與一般事件在結構上無法區分。

---

## 保險機制

8. **`min_app_version` 的使用約定**
   App 端這輪會讀取並尊重該欄位。

9. **提供 fixture**：manifest、`calendar.json`、events 切片各一份，供兩邊契約測試使用。

---

## 明確不要做

- **不要把起點 00:00 的有時刻事件壓成全天。** 那 22 筆的結束時刻是真資訊
  （17:00 共 13 筆、21:00 共 7 筆、23:59 共 2 筆），壓成全天會丟掉截止時間。
  這屬於 App 呈現層，且現況與換源無關。
- **不要補週末標記。** App 端自算。

---

## 需要回覆 App 端的一個確認

**發布端的 quality gate 是否為全有全無、驗不過就不覆寫舊版？**

App 端打算把驗證從「8 條不變量全驗」降為結構性檢查，語意正確性交給發布端。
理由是發布端修正的成本是一次 CI，App 端是一次送審。這項確認會決定 App 端的驗證範圍。
