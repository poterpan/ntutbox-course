# crawler — 課程目錄爬蟲（Python）

打公開免登入的 `aps.ntut.edu.tw/course/tw/`，正規化成 typed v1 → 輸出 canonical NDJSON（git）+ 發佈 JSON artifacts（→ Cloudflare R2）。跑在 GitHub Actions（cron）。

- `models.py` — **schema 真相**（Pydantic v2）。同時 `model_json_schema()` 餵 `packages/schema` 產 TS 型別。
- 端點地圖、欄位對映、解析防呆、節次/班級/階段規則：見 `../docs/DESIGN.md`（§1.2 端點、§2 gnehs 參考、§4.5–§4.7 schema/實證）。

## ✅ P0 已完成（2026-06-13）
110-1～115-1 共 11 學期、32,338 課已爬取並通過驗證，產物在 `../data/`。
實作細節與 live 探測結論（stime 必帶、matric 字面格式、課程編碼在列內等）見
`../docs/superpowers/plans/2026-06-13-crawler-p0.md`。

### 使用
```bash
cd crawler
uv venv .venv && uv pip install -p .venv/bin/python -e '.[dev]'
.venv/bin/pytest                                            # 40 tests
.venv/bin/python -m ntut_catalog crawl --terms 115-1 --out ../data          # 單學期（已存在會跳過）
.venv/bin/python -m ntut_catalog crawl --terms 110-1:115-1 --out ../data --force  # 全量重抓
.venv/bin/python -m ntut_catalog rederive --out ../data                     # 離線重建內嵌班級欄位（不重爬）
```
每學期 ~136 請求、~5 分鐘（限流 delay 0.4–0.8s + 指數退避）。

### 模組
- `ntut_catalog/client.py` — HTTP（限流/退避；`stime=0` 等 live 實證參數）
- `ntut_catalog/parse_course_table.py` — 24 欄解析（**表頭文字定位**，勿寫死索引）
- `ntut_catalog/parse_subj.py` / `classes_builder.py` — 系所/班級 + pool kind 分類
- `ntut_catalog/normalize.py` — → `CourseOffering`（placeholder/credit/meeting；內嵌班級 kind/unit/grade 由 directory lookup 填充）
- `ntut_catalog/orchestrator.py` — 每學期：61 系所×QueryCourse + 13 學制碼×全系所（division 對映 + cross-check）；先建 directory 再 normalize
- `ntut_catalog/artifacts.py` — canonical NDJSON + v1 JSON + manifest(sha256)
- `ntut_catalog/rederive.py` — 離線從 classes.json 重建課程內嵌班級欄位（kind/unit/grade），不重爬
- `ntut_catalog/periods.py` — 節次↔牆鐘（官方頁尾表，靜態+爬取時驗證）

## 後續（非 P0）
- 課程描述（`Curr.jsp`）/ 課綱（`ShowSyllabus.jsp`）→ `course/{offeringId}.json` 詳情檔（隨點隨取，P1 需要再爬）
- `SearchMProgram.jsp` 微學程、`Cprog.jsp` 課程標準（requirement.category 對映）
- 選課季 enrollment-only 高頻更新 job

## 注意
- 來源無：單雙週、教室↔節次、容量上限 → 對應欄位 optional/None。
- 依賴：`pydantic>=2`、`httpx`、`beautifulsoup4`、`html5lib`（見 `pyproject.toml`）。
