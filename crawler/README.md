# crawler — 課程目錄爬蟲（Python）

打公開免登入的 `aps.ntut.edu.tw/course/tw/`，正規化成 typed v1 → 輸出 canonical NDJSON（git）+ 發佈 JSON artifacts（→ Cloudflare R2）。跑在 GitHub Actions（cron）。

- `models.py` — **schema 真相**（Pydantic v2）。同時 `model_json_schema()` 餵 `packages/schema` 產 TS 型別。
- 端點地圖、欄位對映、解析防呆、節次/班級/階段規則：見 `../docs/DESIGN.md`（§1.2 端點、§2 gnehs 參考、§4.5–§4.7 schema/實證）。

## ✅ P0 已完成（2026-06-13）
110-1～115-1 共 11 學期、32,338 課已爬取並通過驗證，產物在 `../data/`。
實作細節與 live 探測結論（stime 必帶、matric 字面格式、課程編碼在列內等）見
`../docs/superpowers/plans/2026-06-13-crawler-p0.md`。

### 資料分層（infra 後）
- **canonical（git `data` branch，完整真相）**，逐學期：`catalog.ndjson`（**純結構**，無 enrollment/時間戳）+ `classes.json` + `enrollment/{date|dateTHH}.ndjson`（時序快照，daily date、選課季 hourly）+ `details.ndjson`（描述+大綱）+ `mprograms.json`（微學程）；跨入學年 `standards/{year}.json`（課程標準/畢業標準）。
- **v1（R2、gitignore、由 canonical 重建）**：`v1/terms/{term}/{catalog,classes,periods,enrollment,mprograms}.json` + `v1/terms/{term}/course/{offeringId}.json`（詳情，隨點隨取）+ `v1/standards/{year}.json` + `v1/manifest.json`。**只有 `derive` 產 v1**（先清空再從 canonical 完整重生、確定性、不讀系統時間）；fetch 類子命令只寫 canonical。
- **跨學期 top-level**：`canonical/calendar/{events.ndjson,meta.json}` → `v1/calendar/events.json`（行事曆事件 feed，契約四）。內容沒變就不重寫 → `data` branch 上每個 `data(calendar)` commit 都代表學校真的改了行事曆。
- **週次表（逐學期）**：`canonical/{term}/calendar.json` → `v1/terms/{term}/calendar.json`（契約三）。**不綁課程目錄是否已爬**——下學期的週次表往往早於課程目錄就能產。
- **逐週進度**：`Syllabus.weekly_progress` inline 在 `details.ndjson` 裡（契約一），隨既有管線自動流到 `course/{id}.json`。三態統計寫 `canonical/reports/{term}/weekly-progress.json`。
- catalog 純結構 → 結構沒變則每日零 diff；enrollment 變動只進 snapshot（時序）。`requirement.category` 由符號圖例（Cprog -5）於 normalize 補。

### 使用
```bash
cd crawler
uv venv .venv && uv pip install -p .venv/bin/python -e '.[dev]'
.venv/bin/pytest                                                    # 422 tests
.venv/bin/python -m ntut_catalog current-term                       # 偵測當前學期（印 115-1）
.venv/bin/python -m ntut_catalog crawl --terms 115-1 --out ../data --force   # 爬目錄 + 寫 snapshot（只寫 canonical）
.venv/bin/python -m ntut_catalog derive --out ../data                         # canonical → v1（publish 前必跑）
.venv/bin/python -m ntut_catalog crawl --terms 110-1:115-1 --out ../data     # 全量 backfill（skip 已存在 canonical）
.venv/bin/python -m ntut_catalog crawl-detail --terms 115-1 --out ../data    # 描述(Curr)+大綱(ShowSyllabus) → details.ndjson
.venv/bin/python -m ntut_catalog crawl-mprograms --terms 115-1 --out ../data # 微學程(SearchMProgram) → mprograms.json
.venv/bin/python -m ntut_catalog crawl-standards --years 115 --out ../data   # 課程標準/畢業標準(Cprog -2→-3→-4) → standards/{year}.json
.venv/bin/python -m ntut_catalog crawl-calendar --out ../data       # 校網 Google Calendar ics → 事件 feed + 當前學年度週次表
.venv/bin/python -m ntut_catalog reprocess-progress --terms 115-1 --out ../data  # 離線重算逐週進度（parser 升版後用，不重爬）
.venv/bin/python -m ntut_catalog recategorize --out ../data         # 離線依符號補 requirement.category（不重爬）
.venv/bin/python -m ntut_catalog migrate --out ../data              # 既有資料→structural+snapshot（一次性，不重爬）
.venv/bin/python -m ntut_catalog refresh-enrollment --terms 115-1 --out ../data  # 選課季輕量人數刷新（~62 請求，hourly 快照）
.venv/bin/python -m ntut_catalog rederive --out ../data             # 離線重建內嵌班級欄位（不重爬）
```
每學期 ~136 請求、~5 分鐘（限流 delay 0.4–0.8s + 指數退避）。skip/resume 看 **canonical**；daily 一律 `--force` 以刷新 enrollment。

### 模組
- `ntut_catalog/client.py` — HTTP（限流/退避；`stime=0`）+ `detect_current_term`（讀 QueryCurrPage 下拉）
- `ntut_catalog/parse_course_table.py` — 24 欄解析（**表頭文字定位**，勿寫死索引）
- `ntut_catalog/parse_subj.py` / `classes_builder.py` — 系所/班級 + pool kind 分類
- `ntut_catalog/normalize.py` — → `CourseOffering`（內嵌班級 kind/unit/grade 由 directory lookup 填充）
- `ntut_catalog/orchestrator.py` — 每學期：61 系所×QueryCourse + 13 學制碼×全系所；先建 directory 再 normalize
- `ntut_catalog/artifacts.py` — `structural_*`（去 volatile，非 mutate）/ `write_canonical` / `derive`（清空 v1 → `build_v1` 從全部 canonical 重建）/ `write_manifest`（dataset_version=結構 sha）
- `ntut_catalog/parse_detail.py` / `detail.py` — Curr(描述/EN)+ShowSyllabus(大綱)解析；`crawl_detail`（Curr 依 course_code 去重）+ `write_details`
- `ntut_catalog/parse_program.py` / `programs.py` — 微學程(SearchMProgram)+課程標準(Cprog -2→-3→-4)解析與爬取
- `ntut_catalog/requirement_legend.py` — 符號→必/選類別（Cprog -5 全域圖例）；normalize 套用
- `ntut_catalog/parse_progress.py` — 課程進度自由文字 → 逐週進度（契約一／二）。移植自 POC 並加三條規則：雙語配對／編號＋日期表／純日期清單。**拒絕沒有日期佐證的純編號清單**（那多半是章節）
- `ntut_catalog/registry.py` — 資料集登錄表（唯一宣告處）；`pipeline.py`（fetch）、`merge.py`（上鎖合併）、`fetch_state.py`、`enrollment_store.py`
- `ntut_catalog/migrate_v2.py` — 一次性遷移到管線 v2（`migrate-pipeline-v2`；切換後刪除）
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
- `../.github/workflows/maintenance.yml` — 僅 dispatch：`backfill`（任何資料集＋學期，details 走 matrix）／`republish`（derive＋publish，含 dry-run、`allow_mass_delete`）／`migrate`（一次性，切換後移除）。
- `../.github/workflows/test.yml` — push/PR 跑 pytest + 檢查 `packages/schema` 產物與 `models.py` 同步。**在此之前 repo 沒有任何跑測試的 CI。**
- `../infra/publish.py`（純上傳：線上 manifest 品質閘門 + 全量 MD5 比對 + manifest 最後推 + 過期刪除與 10% 保險，見檔頭）、`redline_scan.py`（free-text 跳過 student-id 啟發）、`calendar_horizon_alert.py`（行事曆涵蓋不足→開 issue，補上→自動關；告警不阻斷發布）、`SETUP.md`。

## 後續（非本輪）
- 對外 `.ics` 匯出（讓使用者訂閱自己的課表）。
- 退選率分析（衍生自 enrollment 時序 snapshots）。
- standards 的「新學期自動爬取」掛入排程（目前手動；無 web 消費者，暫緩）。
  （mprograms 已入每日排程 #41、detail 已入週更 #47。）
- 較早入學年的 standards backfill（目前僅 115）。

## 注意
- 來源無：單雙週、教室↔節次、容量上限 → 對應欄位 optional/None。
- 依賴：`pydantic>=2`、`httpx`、`beautifulsoup4`、`html5lib`（見 `pyproject.toml`）。
