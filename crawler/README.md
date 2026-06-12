# crawler — 課程目錄爬蟲（Python）

打公開免登入的 `aps.ntut.edu.tw/course/tw/`，正規化成 typed v1 → 輸出 canonical NDJSON（git）+ 發佈 JSON artifacts（→ Cloudflare R2）。跑在 GitHub Actions（cron）。

- `models.py` — **schema 真相**（Pydantic v2）。同時 `model_json_schema()` 餵 `packages/schema` 產 TS 型別。
- 端點地圖、欄位對映、解析防呆、節次/班級/階段規則：見 `../docs/DESIGN.md`（§1.2 端點、§2 gnehs 參考、§4.5–§4.7 schema/實證）。

## P0 第一個任務（建議起點）
1. 實作 `QueryCourse.jsp` POST（依 學制×系所 分頁）+ `Curr.jsp`(描述) + `ShowSyllabus.jsp`(課綱) + `Subj.jsp`(班級) + `SearchMProgram.jsp`(微學程)。
2. 解析 → `CourseOffering`（**表頭文字定位欄位，勿寫死索引**；html5lib 容錯；`<a>` 缺失 null 不回退）。
3. 跑一學期完整爬取 → 產 `catalog.json` / `classes.json` / `periods.json` / `enrollment.json`，用 `models.py` 驗證（pydantic `model_validate`）。
4. 限流自保（每請求 delay + 退避重試；增量：course_code 未變則跳過描述/課綱）。

## 注意
- 來源無：單雙週、教室↔節次、容量上限 → 對應欄位 optional/None。
- bootstrap 期可先讀 gnehs gh-pages JSON 驗 UX，但**正式自爬**；讀 gnehs 要按課號去重 + pangu 空白 normalize。
- 依賴：`pydantic>=2`、`requests`/`httpx`、`beautifulsoup4`、`html5lib`、`lxml`。
