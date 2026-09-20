# 發布端回覆：行事曆事件與學年度週次表

2026-09-19｜回覆 `2026-09-19-calendar-source-app-handoff.md`｜對應 poterpan/NTUTBox#181、#168

**必修 1、3 已完成並上線，必修 2 退回；建議 6、9 一併做。** 另修掉一個你們沒提、但會讓 App
整份拒收的矛盾。全部改動已合併至 `main`，`crawl-calendar.yml` 實跑驗證過。

---

## 已完成

### 必修 3 — 2027-08-01 的管線死亡（你們抓到的最重要一項）

已重現確認：`default_terms()` 在 2027-08-01 會要求 116 學年度，而 ics 那時多半還沒有。
原本全有全無 + CLI 沒接例外 → `crawl-calendar` 非零退出 → **事件 feed 一起停更**。

改成區分兩種失敗：

| 狀況 | 處理 |
|---|---|
| 窗口內零事件（`TermNotPublishedYet`） | 安靜跳過；全部都空就回空、**保留既有週次表不動** |
| 有事件但湊不出合法週次表 | **仍然硬錯、仍然全有全無** |

前者是常態（112 學年度下學期拖到 2024-02），後者代表規則或來源壞了。

### 必修 1 — 週次表發布不再綁課程目錄

`terms/115-2/calendar.json` 現在是 **200**（先前 404）。週次表只需要行事曆、不需要課程目錄，
綁 `--terms` 會讓下學期的永遠停在本機。改成有產出就發佈，範圍仍由推導決定、**不需要任何人
手動設定**。

**發現機制**（你們 2026-09-19 的追加回覆）：已做，見下方「manifest.calendars」一節。

### 你們沒提、但會讓 App 整份拒收的一項

manifest 裡 calendar entry 的 `schema_version` 原本沿用全域值 **2**，而 `calendar.json`
檔案自己宣告 **1**（獨立版本，刻意不跟全域綁，免得課程 schema 改版害行事曆被拒收）。

兩邊不一致，而你們的 decoder 對版本不符是整份拒收 —— 會是靜默失效。已改成走
`CALENDAR_SCHEMA_VERSION`，並加測試斷言「manifest 宣告的版本 == 檔案宣告的版本」。
線上現已是 `1`。

### 建議 6 — 涵蓋範圍驗證

新增 `infra/calendar_coverage_check.py`，掛在 `crawl-calendar.yml`：

```
horizon         量 ics 來源的日期涵蓋到多遠
coverage check  量已發布的 artifact 涵蓋哪些學期
```

你們指出的盲點成立 —— 2026-09-19 當下 `horizon.ok == true` 與 115-2 的 404 確實並存。
只告警不阻斷（8 月缺學期是常態）。

### 建議 9 — fixture

`crawler/tests/fixtures/calendar/` 三份：`manifest.json`、`calendar-115-1.json`、
`events-sample.json`（四種事件形態各一：全天單日／全天跨日／有時刻／缺 `DTEND`）。
有測試確認三份互相一致。

---

### manifest.calendars — 發現機制

你們的顧慮成立：我原本建議「App 直接 conditional GET」等於把 8/1 學年度界線複製進
**需要送審才能改**的那一側。那正是契約三要避開的事。

照你們的提案做了，**純新增、不動 `ManifestTerm`、不必 bump 版本**：

```json
"calendars": {
  "115-1": { "url": "terms/115-1/calendar.json", "sha256": "…", "size": 1823,
             "schema_version": 1,
             "first_week_start": "2026-09-06", "last_week_end": "2027-01-09" },
  "115-2": { …, "first_week_start": "2027-02-21", "last_week_end": "2027-06-26" }
}
```

**多帶了涵蓋範圍**，因為只給清單的話 App 仍然要在 115-1 與 115-2 之間挑一個——那條規則
又回到 App 裡了。有範圍的話，App 的規則只剩**通用的日期比對**：找範圍涵蓋今天的那一筆，
然後精準抓一個檔。學期代號的算法一條都不進 App。

三件要知道的：

- **範圍是授課週**（第 1 週起日 ~ 末週迄日），不含準備週與假期。學期之間（1/11~1/31）
  不會有任何一筆涵蓋今天——那是真實的空窗，不是資料缺漏。要做「距離開學還有幾天」的話，
  挑「起日在未來且最近」的那筆。
- **清單限當前與前一學年度，最多 4 筆、永遠不會長大。** 留前一年是為了填住 8 月的洞：
  新學年度的 ics 還沒匯入時，只留當前的話清單會是空的。
- **舊的 `calendar.json` 檔案照舊留在 CDN、不刪**，只是不列進清單。直接知道 URL 打得到。
  清單是發現機制，不是歷史檔案館。

`terms[].calendar` 保留不動，與 `calendars` 由同一次計算產生、不可能漂移。
**`calendars` 是權威的發現清單。**

## 必修 2 退回：全天結束日維持 inclusive

理由是**跨端點一致性**，不是偷懶。

`calendar.json` 的 `weeks[].end` **結構上必須是 inclusive**：第 1 週是 `09-06 → 09-12`
（週日到週六）。沒有人會把一週的結束寫成下一個週日。`midterm`、`final_exam`、
`flexible_learning` 同理。

如果 `events.json` 改成 exclusive，App 會同時面對兩種日期語意 —— 同一個 app、同一個
「日期區間」概念、兩套規則。那比「在邊界轉一次」更容易出錯。

另外：exclusive 的失敗模式是單日事件變成零長度、**整筆消失且不報錯**，那正是 #180 的形狀；
inclusive 的失敗模式是少一天，看得見。

payload 已宣告 `range_end_semantics: "inclusive"`，轉換一行：

```swift
let endExclusive = Calendar.current.date(byAdding: .day, value: 1, to: endDate)!
```

**如果你們仍要 exclusive**，我照做，但有兩個附帶條件：`calendar.json` 要一起改（否則就是
上面說的兩套語意，而 `weeks[].end` 改成 exclusive 會非常反直覺），以及要 bump
`schema_version`（你們的 decoder 對版本不符是整份拒收，這是協調式發版）。

---

## 回覆你們的確認：quality gate 是全有全無嗎？

**是，而且是 pre-flight 不是 rollback。** 推導或不變量失敗 → 直接拋錯、**不寫出任何產物**
→ 上傳階段沒有新檔案 → R2 舊物件原封不動。與 `infra/publish.py` 的 `quality_gate` 同語意
（擋在任何上傳之前 `return 1`）。

所以你們把驗證降為結構性檢查是安全的。**前提是必修 3 要先修** —— 沒修的話「失敗就保留舊版」
在 2027-08-01 之後會變成「永遠保留舊版」，因為每天都失敗。已修完，前提成立。

---

### 時間戳的語意（2026-09-20 補）

三個 `generated_at` 的差異是刻意的：

| 檔案 | `generated_at` | 內容變動的時間在哪 |
|---|---|---|
| `manifest.json` | 有值 | —（索引檔，`max-age=300`，本來就常變） |
| `calendar/events.json` | `null` | `source.fetched_at` |
| `terms/{term}/calendar.json` | `null` | `source.parsed_at` |
| `catalog.json` | `null` | —（repo 既有慣例） |

**不帶建置時間戳**是為了讓內容沒變的日子 byte-identical、ETag 不變、你們拿得到 304。
兩個 `source.*_at` 現在的語意都是**內容最後一次變動的時間**，不是最後一次跑的時間 ——
所以它們可以直接當「這份資料多舊」用。

## 兩項訂正

- **建議 5（manifest `generated_at` 為 null）**：現況不是 null，實測 `2026-09-18T22:30:22Z`。
  可能是你們驗的時候剛好在某次發佈之前。`min_app_version` 確實是 null。
- **`min_app_version` 的約定**：目前維持 null＝不設下限。只有在發生破壞性變更時才填入
  「能讀懂新 schema 的最低 App 版本」，並同時 bump 對應的 `schema_version`。
  換句話說，看到它是 null 就代表沒有版本下限，不是「還沒實作」。

## 未做

- **建議 7（`is_holiday`）延後，而且要小心**：ics 沒有結構化的假日標記，判斷國定假日只能
  比對「國慶日／補假／放假」這類中文關鍵字 —— 那正是這輪一直在消滅的耦合
  （你們自己在 #181 也指出 App 有三處靠中文關鍵字反推語意會靜默失效）。
  要做的話應該另起一輪調查，先確認有沒有非字串的判據。
- **115-2 進 manifest**：見上。
