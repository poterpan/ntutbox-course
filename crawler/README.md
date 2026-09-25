# crawler — 課程目錄爬蟲（Python）

打公開免登入的 `aps.ntut.edu.tw/course/tw/`，正規化成 typed v1 → 輸出 canonical NDJSON（git）+ 發佈 JSON artifacts（→ Cloudflare R2）。跑在 GitHub Actions（cron）。

- `models.py` — **schema 真相**（Pydantic v2）。同時 `model_json_schema()` 餵 `packages/schema` 產 TS 型別。
- 端點地圖、欄位對映、解析防呆、節次/班級/階段規則：見 `../docs/DESIGN.md`（§1.2 端點、§2 gnehs 參考、§4.5–§4.7 schema/實證）。

## ✅ P0 已完成（2026-06-13）
110-1～115-1 共 11 學期、32,338 課已爬取並通過驗證，產物在 `../data/`。
實作細節與 live 探測結論（stime 必帶、matric 字面格式、課程編碼在列內等）見
`../docs/superpowers/plans/2026-06-13-crawler-p0.md`。

### 資料分層（管線 v2，2026-09-26 起）
三層邊界（fetch 只寫 canonical、derive 只產 v1／reports、publish 只上傳）與理由見 `../docs/DECISIONS.md` D11–D16。
- **canonical（git `data` branch，完整真相，只記內容、不記爬取時間）**，逐學期：`catalog.ndjson`（**純結構**，無 enrollment/時間戳）+ `classes.json` + `enrollment/`（人數時序，見下）+ `details.ndjson`（描述+大綱原文，**不含**逐週進度）+ `mprograms.json`（微學程）；跨入學年 `standards/{year}.json`（課程標準/畢業標準）。
- **`_meta/fetch-state.json`**：每個 (資料集, 學期) 的 `checked_at`／`changed_at`／`content_sha256`（無學期維度用 `_global` 鍵）。由鎖內的 merge 對最新 HEAD 更新；derive 把它帶進 manifest 各產物的 `checked_at`／`changed_at`。
- **v1（R2、gitignore、由 canonical 重建）**：`v1/terms/{term}/{catalog,classes,periods,enrollment,mprograms}.json` + `v1/terms/{term}/course/{offeringId}.json`（詳情，隨點隨取）+ `v1/standards/{year}.json` + `v1/manifest.json`。**只有 `derive` 產 v1**（先清空再從 canonical 完整重生、確定性、不讀系統時間）；`pipeline` 只寫 canonical。
- **跨學期 top-level**：`canonical/calendar/{events.ndjson,meta.json}` → `v1/calendar/events.json`（行事曆事件 feed，契約四）。內容沒變就不重寫。
- **週次表（逐學期）**：`canonical/{term}/calendar.json` → `v1/terms/{term}/calendar.json`（契約三）。**不綁課程目錄是否已爬**——下學期的週次表往往早於課程目錄就能產。
- **逐週進度**：derive 產 `course/{id}.json` 時由課綱原文 × 週次表即時計算（契約一），行事曆或 parser 改了下次 derive 自動生效；三態統計寫 `canonical/reports/{term}/weekly-progress.json`（commit 進 data branch，數字沒變就不 commit）。
- `requirement.category` 由符號圖例（Cprog -5）於 normalize 補。

### 人數時序（enrollment store）
讀寫一律經 `ntut_catalog/enrollment_store.py`（換儲存只改這支）：
- **快照** `canonical/{term}/enrollment/YYYY-MM-DDTHHMM.ndjson`：一行一課 `{offering_id, enrolled_count, withdrawn_count}`，檔名＝台北時間精確到分，**列內不帶時間**；與前一份內容相同就不寫；永不改寫、永不刪除。
- **觀測紀錄** `canonical/{term}/enrollment/observations.ndjson`：每次成功爬取追加一行 `{"observed_at": "…+08:00", "snapshot": "2026-09-07T1000"}`——分得出「確認過、數字沒變」與「沒爬到」。
- **讀取**：`latest(term_dir) -> (rows, observed_at)`、`history(term_dir) -> Iterator[(observed_at, rows)]`。v1 `enrollment.json` 的 `observed_at`（頂層與每列）＝最後一筆觀測時間。
- **寫入分兩段**：fetch（不上鎖）只 `write_candidate`；鎖內 merge 才 `write_snapshot`（對最新 HEAD 去重）＋`append_observation`。daily（catalog 順帶記人數）與 season（enrollment）會寫同一學期，去重必須在鎖內做。

### 資料集登錄表（`ntut_catalog/registry.py`）
每個資料集**唯一**的宣告處：`DATASETS` 裡一筆 `Dataset(name, cadence, terms, fetch, writes, append_only, content)`。
workflow 依 cadence 跑、merge 依 `writes` 決定哪些檔可進 data branch（`git add` 範圍也由它產生）、fetch-state 依 `content` 算 hash。

| name | cadence | terms | writes |
|---|---|---|---|
| `calendar` | daily | calendar（fetcher 自決學期） | `calendar/events.ndjson`、`calendar/meta.json`、`{term}/calendar.json` |
| `catalog` | daily | active | `{term}/catalog.ndjson`、`{term}/classes.json`、`{term}/enrollment/*.ndjson`（append_only：`observations.ndjson`） |
| `mprograms` | daily | active | `{term}/mprograms.json` |
| `details` | weekly | current | `{term}/details.ndjson` |
| `standards` | weekly | none | `standards/*.json`（入學年＝當前學年與前 5 學年） |
| `enrollment` | season | current（season 一律要明確給 terms） | `{term}/enrollment/*.ndjson`（append_only 同上） |

學期規則：`active` = repo var `ACTIVE_TERMS`（可用範圍語法），未設則同 `current`；`current` = `current-term` 偵測（QueryCurrPage 預設學期，選課季可能仍是上一學期）；`calendar`／`none` 跑一次、fetch-state 用 `_global` 鍵。明確給 `--terms` 一律優先。

**新增一個資料集**（不新增 workflow 檔、不新增子命令）：
1. **fetcher**：在 `registry.py` 寫 `fetch_xxx(ctx: FetchContext, term) -> FetchOutput`，包既有爬取程式、只寫 canonical；`FetchOutput.files` 回報實際寫出的檔（必須落在 `writes` 內，否則 pipeline 直接判失敗）。逐節點爬的要回報 `failed_nodes`／`node_total`（D16）。
2. **v1 builder**：在 `artifacts.py` 的 `build_v1`（由 `derive` 呼叫）加上 canonical → `v1/` 的轉換；需要 freshness 的話在 `write_manifest` 對應產物。
3. **登錄表一筆**：`DATASETS` 加 `Dataset(...)`——`cadence`（daily／weekly／season／manual；同層耗時要相近，慢的換層）、`terms`（學期規則）、`writes`（canonical 相對路徑樣板，`{term}`／`*`）、`append_only`（要追加而非覆寫的檔）、`content`（算 `content_sha256` 的檔）。
4. 測試：`tests/test_pipeline.py`／`tests/test_merge.py` 有假 client 的範例可照抄。

### CLI
```bash
cd crawler
uv venv .venv && uv pip install -p .venv/bin/python -e '.[dev]'
.venv/bin/pytest
.venv/bin/python -m ntut_catalog current-term                          # 偵測當前學期（印 115-1）
# fetch：跑登錄表同 cadence 的資料集，只寫 canonical＋<out>/stage/pipeline-result.json
.venv/bin/python -m ntut_catalog pipeline --cadence daily --out ../data
.venv/bin/python -m ntut_catalog pipeline --cadence manual --datasets details --terms 115-1 --out ../data
.venv/bin/python -m ntut_catalog pipeline --cadence season --terms 115-2 --out ../data   # season 的 --terms 必填
.venv/bin/python -m ntut_catalog pipeline --cadence daily --out ../data --merge          # 本機一次做完 fetch＋merge
# merge：stage → 最新 canonical（CI 的上鎖 job 跑這個；去重、fetch-state、節點失敗規則都在這裡）
.venv/bin/python -m ntut_catalog merge --stage ../data/stage --out ../data
# derive：canonical → v1（全量、確定性；publish 前必跑）
.venv/bin/python -m ntut_catalog derive --out ../data
.venv/bin/python -m ntut_catalog pua-scan --terms 115-1 --out ../data  # 新造字碼位監測
```
- `--datasets` 未給＝該 cadence 全部；給了可跨 cadence（補爬用，搭配 `--cadence manual`）。`--terms` 支援 `110-1:115-1` 範圍與逗號。
- 結束碼：`0` 全部成功、`1` 有資料集失敗（成功的照常可 merge）、`2` 用法錯誤（如 season 沒給 `--terms`）。
- 每學期 catalog ~136 請求、~5 分鐘（限流 delay 0.4–0.8s + 指數退避）；details 單學期約 53 分鐘。
- 2026-09 已移除的舊子命令（`crawl`／`crawl-detail`／`crawl-mprograms`／`crawl-standards`／`crawl-calendar`／`refresh-enrollment`／`reprocess-progress` 與一次性的 `migrate*`／`rederive`／`rematric`／`recategorize`）一律改用上面的 `pipeline --datasets …`。

### 模組
- `ntut_catalog/client.py` — HTTP（限流/退避；`stime=0`）+ `detect_current_term`（讀 QueryCurrPage 下拉）
- `ntut_catalog/parse_course_table.py` — 24 欄解析（**表頭文字定位**，勿寫死索引）
- `ntut_catalog/parse_subj.py` / `classes_builder.py` — 系所/班級 + pool kind 分類
- `ntut_catalog/normalize.py` — → `CourseOffering`（內嵌班級 kind/unit/grade 由 directory lookup 填充）
- `ntut_catalog/orchestrator.py` — 每學期：61 系所×QueryCourse + 13 學制碼×全系所；先建 directory 再 normalize
- `ntut_catalog/artifacts.py` — `structural_*`（去 volatile，非 mutate）/ `write_canonical` / `derive`（清空 v1 → `build_v1` 從全部 canonical 重建）/ `write_manifest`（dataset_version=結構 sha；freshness 取自 fetch-state）
- `ntut_catalog/parse_detail.py` / `detail.py` — Curr(描述/EN)+ShowSyllabus(大綱)解析；`crawl_detail`（Curr 依 course_code 去重）+ `write_details`（只寫 canonical）
- `ntut_catalog/parse_program.py` / `programs.py` — 微學程(SearchMProgram)+課程標準(Cprog -2→-3→-4)解析與爬取
- `ntut_catalog/requirement_legend.py` — 符號→必/選類別（Cprog -5 全域圖例）；normalize 套用
- `ntut_catalog/parse_progress.py` — 課程進度自由文字 → 逐週進度（契約一／二）。移植自 POC 並加三條規則：雙語配對／編號＋日期表／純日期清單。**拒絕沒有日期佐證的純編號清單**（那多半是章節）
- `ntut_catalog/registry.py` — 資料集登錄表（唯一宣告處，見上）；`pipeline.py`（fetch）、`merge.py`（上鎖合併＋節點失敗規則）、`fetch_state.py`、`enrollment_store.py`、`nodes.py`（節點失敗計數）
- `ntut_catalog/periods.py` — 節次↔牆鐘（官方頁尾表，靜態+爬取時驗證）
- `ntut_catalog/ics.py` / `calendar_client.py` / `calendar_events.py` — 校網 Google Calendar ics 解析（全天 end-exclusive→inclusive、缺 DTEND、UTC→+08:00、穩定排序）+ 外部主機 client + feed 組裝與 horizon 監測
- `ntut_catalog/term_calendar.py` — 學年度週次表：從 ics 具名事件推導（第 1 週＝開學日所在週、週日起算；末週＝假期起日前一個週六所在週）+ 10 條不變量。**不解析 PDF**；`reference/pdf-week-tables-111-115.json` 是從校方公告 PDF 抽出的 10 學期回歸基準，在**發佈時**跑

### 自動化 / 發佈
依頻率分 4 支（資料管線 v2，spec `docs/superpowers/specs/2026-09-26-data-pipeline-refactor-design.md` §3）；
每支都是「fetch job（不上鎖）→ commit-publish job（`data-pipeline` 鎖）→ alert job」，共用 `../.github/actions/{setup,commit-publish,alert}`。
跑哪些資料集由 `ntut_catalog/registry.py` 的 cadence 決定，新增資料集不改 workflow。
- `../.github/workflows/daily.yml` — 每日 cron 04:00：calendar、catalog＋人數、mprograms；另跑行事曆 horizon／coverage 與資料過期檢查。
- `../.github/workflows/weekly.yml` — 每週一 05:30：details（課綱）、standards。
- `../.github/workflows/season.yml` — 僅 dispatch：選課季人數刷新（`terms` 必填）。
- `../.github/workflows/maintenance.yml` — 僅 dispatch：`backfill`（任何資料集＋學期，details 走 matrix）／`republish`（derive＋publish，含 dry-run、`allow_mass_delete`）。操作手冊見 `../infra/README.md`「維運 runbook」。
- `../.github/workflows/test.yml` — push/PR 跑 pytest + 檢查 `packages/schema` 產物與 `models.py` 同步。**在此之前 repo 沒有任何跑測試的 CI。**
- `../infra/publish.py`（純上傳：線上 manifest 品質閘門 + 全量 MD5 比對 + manifest 最後推 + 過期刪除與 10% 保險，見檔頭）、`redline_scan.py`（free-text 跳過 student-id 啟發）、`calendar_horizon_alert.py`（行事曆涵蓋不足→開 issue，補上→自動關；告警不阻斷發布）、`pipeline_alert.py`（`pipeline-alert` issue：run 失敗與資料過期）、`data_commit.py`（commit 訊息／範圍）、`SETUP.md`。

## 後續（非本輪）
- 對外 `.ics` 匯出（讓使用者訂閱自己的課表）。
- 退選率分析（衍生自 enrollment 時序 snapshots）。
- season 的 Cloudflare Cron 觸發＋選課窗口從行事曆自動判斷（目前 `season.yml` 只能手動 dispatch；115-2 網路選課前完成）。
- 空教室（rooms）資料集——登錄表的一筆。

## 注意
- 來源無：單雙週、教室↔節次、容量上限 → 對應欄位 optional/None。
- 依賴：`pydantic>=2`、`httpx`、`beautifulsoup4`、`html5lib`（見 `pyproject.toml`）。
