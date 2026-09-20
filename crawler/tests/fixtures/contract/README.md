# 契約樣本（發布端 ↔ iOS App）

這裡的 JSON 是**由現行 parser 產出**的發布格式樣本，給 App 端手寫 `Codable`
對照用（`docs/research/2026-09-06-course-content-and-weekly-progress-handoff.md` §7）。
`crawler/tests/test_contract_fixtures.py` 會比對「樣本 == parser 現在的產出」，
所以它不會靜默過期；刻意改契約時用 `pytest --update-contract-fixtures` 重寫。

## `course-detail-115-1.json`

與 CDN 上的 `course/{offering_id}.json` **同一個形狀**（`models.CourseDetail`）。

- **識別碼是佔位值**：`offering_id` `999999`、第三位「樣本教師」是合成的。
  有契約價值的是欄位形狀，不是這門課真的存在。
- 三位教師刻意涵蓋三種形態：①完整彈性學習（五欄）②沒有彈性學習（空陣列）
  ③重複 `label` + 非空 `extra`。**②③ 是 decoder 最容易寫錯的兩種。**
- **與 `../weekly_progress/course-*.json` 互補、不重疊**：那四份的主題是 `weekly_progress`
  的三態，`flex_learning` 一律是空的；這份是唯一有內容的彈性學習樣本。
  這份的 `weekly_progress` 則是 `null`（parse_syllabus 不負責產它）。

`flex_learning` / `extra` 的不變量（schema v3 起）：

| 不變量 | 意思 |
|---|---|
| 有序 | 陣列順序＝來源表格列序，照序渲染即可，不必知道欄位名 |
| `value` 非空白 | 發布端已濾掉空值列，App 不必再過濾一次 |
| `label` 可能重複 | 不可當 key／不可塞進 Dictionary，否則會靜默掉資料 |
| 欄位名原樣 | 不映射、不正規化；校方改名或增欄位時 App 不用改一行 |
