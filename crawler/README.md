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
- **canonical（git `data` branch，完整真相，只記內容、不記爬取時間）**，逐學期：`catalog.ndjson`（**純結構**，無 enrollment/時間戳）+ `classes.json` + `enrollment/`（人數時序，見下）+ `details.ndjson`（描述+大綱原文，**不含**逐週進度）+ `mprograms.json`（微學程）+ `rooms.json`（教室課表，見下「教室課表」）；跨入學年 `standards/{year}.json`（課程標準/畢業標準）。
- **`_meta/fetch-state.json`**：每個 (資料集, 學期) 的 `checked_at`／`changed_at`／`content_sha256`（無學期維度用 `_global` 鍵）。由鎖內的 merge 對最新 HEAD 更新；derive 把它帶進 manifest 各產物的 `checked_at`／`changed_at`。
- **v1（R2、gitignore、由 canonical 重建）**：`v1/terms/{term}/{catalog,classes,periods,enrollment,mprograms,rooms}.json` + `v1/terms/{term}/course/{offeringId}.json`（詳情，隨點隨取）+ `v1/standards/{year}.json` + `v1/manifest.json`。**只有 `derive` 產 v1**（先清空再從 canonical 完整重生、確定性、不讀系統時間）；`pipeline` 只寫 canonical。
- **跨學期 top-level**：`canonical/calendar/{events.ndjson,meta.json}` → `v1/calendar/events.json`（行事曆事件 feed，契約四）。內容沒變就不重寫。
- **週次表（逐學期）**：`canonical/{term}/calendar.json` → `v1/terms/{term}/calendar.json`（契約三）。**不綁課程目錄是否已爬**——下學期的週次表往往早於課程目錄就能產。含 `enrollment_windows`（kind：`preselection` 預選＝校方「網路選課」／`freshman_preselection` 新生預選／`post_start_add_drop` 開學後加退選＝校方「加選及無紀錄退選」／`midterm_withdrawal` 期中撤選，日夜分開）。窗口放在**發生的學期**的檔（開始日所在學期），`target_term`＝被選的學期：115-2 預選 12/07 在 115-1 的檔、target 115-2；116-1 預選 2027-05-24 在 115-2 的檔、target 116-1。
- **season 排程**：derive 把 manifest `calendars` 範圍內學期的 `enrollment_windows` 展開成整點觸發格（slot `terms`＝窗口的 `target_term`、`windows`＝顯示名 預選／新生預選／開學後加退選／期中撤選）→ `data/ops/season-schedule.json`（v1 之外、確定性）→ publish 傳 `course/ops/season-schedule.json`，Cloudflare Worker 讀它觸發 `season.yml`（`ntut_catalog/season_schedule.py`、D18）。
- **manifest `term_schedule`**（D21）：`{"current": [{"term","from"}…], "default": [{"term","from"}…]}`，client 取 `from ≤ now` 的最後一筆。`current`＝本學期（8/1～1/31 上學期、2/1～7/31 下學期）；`default`＝網站預設學期，從本學期期中撤選截止（`midterm_withdrawal` 各部別 `end` 取晚者）起改為下學期，無撤選窗口時退用下學期預選 `start` − 14 天。由 derive 從全部 `v1/terms/*/calendar.json` 確定性產生（`ntut_catalog/term_schedule.py`），範圍＝有 catalog 的學期 ∪ 有週次表的學期 ∪ 窗口的 `target_term`。學期可能還沒有 catalog——退路在 client（`apps/web/src/lib/terms/term-schedule.ts`）。純新增欄位、不升 `SCHEMA_VERSION`（D15）。
- **逐週進度**：derive 產 `course/{id}.json` 時由課綱原文 × 週次表即時計算（契約一），行事曆或 parser 改了下次 derive 自動生效；三態統計寫 `canonical/reports/{term}/weekly-progress.json`（commit 進 data branch，數字沒變就不 commit）。
- `requirement.category` 由符號圖例（Cprog -5）於 normalize 補。

### 人數時序（enrollment store）
讀寫一律經 `ntut_catalog/enrollment_store.py`（換儲存只改這支）：
- **快照** `canonical/{term}/enrollment/YYYY-MM-DDTHHMM.ndjson`：一行一課 `{offering_id, enrolled_count, withdrawn_count}`，檔名＝台北時間精確到分，**列內不帶時間**；與前一份內容相同就不寫；永不改寫、永不刪除。
- **觀測紀錄** `canonical/{term}/enrollment/observations.ndjson`：每次成功爬取追加一行 `{"observed_at": "…+08:00", "snapshot": "2026-09-07T1000"}`——分得出「確認過、數字沒變」與「沒爬到」。
- **讀取**：`latest(term_dir) -> (rows, observed_at)`、`history(term_dir) -> Iterator[(observed_at, rows)]`。v1 `enrollment.json` 的 `observed_at`（頂層與每列）＝最後一筆觀測時間。
- **寫入分兩段**：fetch（不上鎖）只 `write_candidate`；鎖內 merge 才 `write_snapshot`（對最新 HEAD 去重）＋`append_observation`。daily（catalog 順帶記人數）與 season（enrollment）會寫同一學期，去重必須在鎖內做。

### 教室課表（`rooms`，空教室查找；D23、DESIGN §4.8）
- **fetch**：`Croom.jsp?format=-2`（清單，失敗＝資料集失敗、0 間 → raise）→ 每間 `format=-3&code=`（週課表，一間＝一個節點 `{"room": code}`）。115-1：231 間、約 232 請求、3 分鐘。
- **canonical `{term}/rooms.json`**：只記學校給的——`code`（Croom 教室碼，跨學期穩定）、`raw`（簡稱原文，如「六教526(e)」）、`full_name`、`capacity`（空白 → null）、`slots: [{day 0..6（0=日）, period, offering_ids（排序）}]`。依 code 排序、不帶時間、一列一間。同一格可有多門課（合開）。
- **節點失敗**：失敗的那一間由 merge 從 HEAD 沿用（逐位元組相同）；HEAD 也沒有就**不寫**（空課表會被當成整週沒課）；> 5% 整筆丟棄。
- **v1 `terms/{term}/rooms.json`（derive）**：每間加 `gis: [{building_id, floor_id, class_number}]` 與 `gis_match`（`rule`／`override`／`building_only`／`floor_only`／`none`），頂層 `gis_snapshot`（GIS 快照的 updateSequence）。規則在 `ntut_catalog/room_gis.py`；GIS 快照 `reference/gis-rooms.json`（由 `../infra/gis/build_snapshot.py` 從本機 ntut-campus-map 產，勿手改）；人工對應 `reference/gis-room-overrides.json`（只收 GIS 名稱可驗證者）。`raw` 永遠保留。
- **語意**：slot＝「**有排課**」，不是「被占用」。沒有 slot ≠ 保證空著——社團借用、補課、會議都不在課表裡；App 文案不可講死。房間只有課程系統的教室（不是 GIS 全部空間）。

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
| `rooms` | weekly | active | `{term}/rooms.json`（教室課表；一間教室＝一個節點） |
| `enrollment` | season | current（season 一律要明確給 terms） | `{term}/enrollment/*.ndjson`（append_only 同上） |

學期規則：`active` = current-term ∪ 有選課窗口 `start ≤ now+30 天`、`end ≥ now` 的學期（`registry.upcoming_window_terms`，窗口讀 canonical `{term}/calendar.json`；天數 env `SELECTION_LEAD_DAYS`，D19）；repo var `ACTIVE_TERMS`（可用範圍語法）有設則為明確覆寫、完全照它；`current` = `current-term` 偵測（QueryCurrPage 預設學期，選課季可能仍是上一學期）；`calendar`／`none` 跑一次、fetch-state 用 `_global` 鍵。明確給 `--terms` 一律優先。

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
# 課數／人數驟減（< HEAD × QUALITY_MIN_RATIO）只對 pipeline-result 的 current_term 丟棄；其他學期照收＋warning（D20）
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
- `ntut_catalog/orchestrator.py` — 每學期：61 系所×QueryCourse + 13 學制碼×全系所；先建 directory 再 normalize。season 人數（`crawl_enrollment`）先全校一次查（`matric=全校13碼, unit=＊`，timeout 180 秒、最多 2 次），失敗退回逐系所，來源記進 pipeline-result 的 `enrollment_source`
- `ntut_catalog/artifacts.py` — `structural_*`（去 volatile，非 mutate）/ `write_canonical` / `derive`（清空 v1 → `build_v1` 從全部 canonical 重建）/ `write_manifest`（dataset_version=結構 sha；freshness 取自 fetch-state；`term_schedule` 見 `term_schedule.py`）
- `ntut_catalog/parse_detail.py` / `detail.py` — Curr(描述/EN)+ShowSyllabus(大綱)解析；`crawl_detail`（Curr 依 course_code 去重）+ `write_details`（只寫 canonical）
- `ntut_catalog/parse_program.py` / `programs.py` — 微學程(SearchMProgram)+課程標準(Cprog -2→-3→-4)解析與爬取
- `ntut_catalog/requirement_legend.py` — 符號→必/選類別（Cprog -5 全域圖例）；normalize 套用
- `ntut_catalog/parse_progress.py` — 課程進度自由文字 → 逐週進度（契約一／二）。移植自 POC 並加三條規則：雙語配對／編號＋日期表／純日期清單。**拒絕沒有日期佐證的純編號清單**（那多半是章節）
- `ntut_catalog/registry.py` — 資料集登錄表（唯一宣告處，見上）；`pipeline.py`（fetch）、`merge.py`（上鎖合併＋節點失敗規則）、`fetch_state.py`、`enrollment_store.py`、`nodes.py`（節點失敗計數）
- `ntut_catalog/periods.py` — 節次↔牆鐘（官方頁尾表，靜態+爬取時驗證）
- `ntut_catalog/ics.py` / `calendar_client.py` / `calendar_events.py` — 校網 Google Calendar ics 解析（全天 end-exclusive→inclusive、缺 DTEND、UTC→+08:00、穩定排序）+ 外部主機 client + feed 組裝與 horizon 監測
- `ntut_catalog/term_calendar.py` — 學年度週次表：從 ics 具名事件推導（第 1 週＝開學日所在週、週日起算；末週＝假期起日前一個週六所在週）+ 10 條不變量。**不解析 PDF**；`reference/pdf-week-tables-111-115.json` 是從校方公告 PDF 抽出的 10 學期回歸基準，在**發佈時**跑。另推導 `enrollment_windows`（關鍵字＋容錯；撤選「開始」與日夜「結束」配對；沒寫時刻 → 日 17:00／夜 21:00，撤選夜間照實證 17:00；推不出來或違反窗口不變量 → 丟棄該窗口＋warning，週次表照常）
- `ntut_catalog/season_schedule.py` — `enrollment_windows` → season 觸發時刻表（頻率常數、同整點合併；derive 呼叫）
- `ntut_catalog/parse_room.py` / `rooms.py` / `room_gis.py` — Croom 清單＋週課表解析（表頭文字定位、看不懂的格子 raise）、`crawl_rooms`／canonical 序列化、教室 → GIS 對應（derive）

### 自動化 / 發佈
依頻率分 4 支（資料管線 v2，spec `docs/superpowers/specs/2026-09-26-data-pipeline-refactor-design.md` §3）；
每支都是「fetch job（不上鎖）→ commit-publish job（`data-pipeline` 鎖）→ alert job」，共用 `../.github/actions/{setup,commit-publish,alert}`。
跑哪些資料集由 `ntut_catalog/registry.py` 的 cadence 決定，新增資料集不改 workflow。
- `../.github/workflows/daily.yml` — 每日 cron 04:00：calendar、catalog＋人數、mprograms；另跑行事曆 horizon／coverage 與資料過期檢查。
- `../.github/workflows/weekly.yml` — 每週一 05:30：details（課綱）、standards、rooms（教室課表）；alert job 另跑 GIS 快照漂移檢查（D23）。
- `../.github/workflows/season.yml` — 僅 dispatch（Cloudflare Worker 依 `course/ops/season-schedule.json` 觸發）：選課季人數刷新（`terms` 必填）。
- `../.github/workflows/maintenance.yml` — 僅 dispatch：`backfill`（任何資料集＋學期，details 走 matrix）／`republish`（derive＋publish，含 dry-run、`allow_mass_delete`）。操作手冊見 `../infra/README.md`「維運 runbook」。
- `../.github/workflows/test.yml` — push/PR 跑 pytest + 檢查 `packages/schema` 產物與 `models.py` 同步。**在此之前 repo 沒有任何跑測試的 CI。**
- `../infra/publish.py`（純上傳：線上 manifest 品質閘門 + 全量 MD5 比對 + manifest 最後推 + 過期刪除與 10% 保險，見檔頭）、`redline_scan.py`（free-text 跳過 student-id 啟發）、`calendar_horizon_alert.py`（行事曆涵蓋不足→開 issue，補上→自動關；告警不阻斷發布）、`pipeline_alert.py`（`pipeline-alert` issue：run 失敗、資料過期、season 窗口學期缺 catalog、season 未依排程執行）、`data_commit.py`（commit 訊息／範圍）、`SETUP.md`。

## 後續（非本輪）
- 對外 `.ics` 匯出（讓使用者訂閱自己的課表）。
- 退選率分析（衍生自 enrollment 時序 snapshots）。
- season 的 Cloudflare Worker（排程與告警的 Python 端已完成，issue #111）。

## 注意
- 來源無：單雙週、教室↔節次、容量上限 → 對應欄位 optional/None。
- 依賴：`pydantic>=2`、`httpx`、`beautifulsoup4`、`html5lib`（見 `pyproject.toml`）。
