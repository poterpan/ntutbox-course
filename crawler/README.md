# crawler — 課程目錄爬蟲（Python）

打公開免登入的 `aps.ntut.edu.tw/course/tw/`，正規化成 typed v1 → 輸出 canonical NDJSON（git）+ 發佈 JSON artifacts（→ Cloudflare R2）。跑在 GitHub Actions（cron）。

- `models.py` — **schema 真相**（Pydantic v2）。同時 `model_json_schema()` 餵 `packages/schema` 產 TS 型別。
- 端點地圖、欄位對映、解析防呆、節次/班級/階段規則：見 `../docs/DESIGN.md`（§1.2 端點、§2 gnehs 參考、§4.5–§4.7 schema/實證）。

## ✅ P0 已完成（2026-06-13）
110-1～115-1 共 11 學期、32,338 課已爬取並通過驗證，產物在 `../data/`。
實作細節與 live 探測結論（stime 必帶、matric 字面格式、課程編碼在列內等）見
`../docs/superpowers/plans/2026-06-13-crawler-p0.md`。

### 資料分層（infra 後）
- **canonical（git `data` branch，完整真相）**：`canonical/{term}/catalog.ndjson`（**純結構**，無 enrollment/時間戳）+ `classes.json` + `enrollment/{date}.ndjson`（**每日時序快照**）。
- **v1（R2、gitignore、由 canonical 重建）**：`v1/terms/{term}/{catalog,classes,periods,enrollment}.json` + `v1/manifest.json`。`build_v1` 從 canonical 完整重生，`enrollment.json` 取最新 snapshot。
- catalog 純結構 → 結構沒變則每日零 diff；enrollment 變動只進 snapshot（時序）。

### 使用
```bash
cd crawler
uv venv .venv && uv pip install -p .venv/bin/python -e '.[dev]'
.venv/bin/pytest                                                    # 51 tests
.venv/bin/python -m ntut_catalog current-term                       # 偵測當前學期（印 115-1）
.venv/bin/python -m ntut_catalog crawl --terms 115-1 --out ../data --force   # 爬 + 寫 snapshot + 重建 v1
.venv/bin/python -m ntut_catalog crawl --terms 110-1:115-1 --out ../data     # 全量 backfill（skip 已存在 canonical）
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
- `ntut_catalog/artifacts.py` — `structural_*`（去 volatile，非 mutate）/ `write_canonical` / `write_enrollment_snapshot` / `build_v1`（canonical→完整 v1）/ `write_manifest`（dataset_version=結構 sha）
- `ntut_catalog/migrate.py` — 既有資料一次性遷移成 structural canonical + seed snapshot
- `ntut_catalog/rederive.py` — 離線從 classes.json 重建內嵌班級欄位（kind/unit/grade）
- `ntut_catalog/periods.py` — 節次↔牆鐘（官方頁尾表，靜態+爬取時驗證）

### 自動化 / 發佈
- `../.github/workflows/crawl.yml` — 每日 cron（自動偵測當前學期）→ commit `data` branch → 發佈 R2。
- `../infra/publish.py`（build-v1 + quality gate + 原子發佈）、`redline_scan.py`、`SETUP.md`（上線步驟）。

## 後續（非 P0）
- 課程描述（`Curr.jsp`）/ 課綱（`ShowSyllabus.jsp`）→ `course/{offeringId}.json` 詳情檔（P1 需要再爬）
- `SearchMProgram.jsp` 微學程、`Cprog.jsp` 課程標準（requirement.category 對映）
- 選課季 enrollment-only 高頻更新 job（見 infra spec「fast-follow」）

## 注意
- 來源無：單雙週、教室↔節次、容量上限 → 對應欄位 optional/None。
- 依賴：`pydantic>=2`、`httpx`、`beautifulsoup4`、`html5lib`（見 `pyproject.toml`）。
