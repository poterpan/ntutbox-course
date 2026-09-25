# 資料管線重構 Implementation Plan

> **For agentic workers:** 依 `~/.claude/playbooks/02-judgment.md` R8：spec 已核准、執行者為高階模型 → 本計畫＝spec＋Task 地圖，不寫逐步程式碼。每顆 Task 由一個 agent 連做（自己跑測試、可多個 commit），合併前做一次整條分支 fresh-context 總審。中途 gate 只有資料遷移（Task 4，自動化驗證＋使用者看報告）。

**Goal:** 把資料管線拆成 fetch／derive／publish 三層、workflow 依頻率收成 5 個，canonical 不含爬取時間，並完成一次性遷移與切換。

**Architecture:** 見 spec §1–§3。登錄表（`registry.py`）是資料集的唯一宣告處；每個 workflow＝不上鎖 fetch job＋上鎖 commit-publish job；derive 全量且確定性；publish 全量比對、只傳差異、刪過期檔。

**Tech Stack:** Python 3.12（Pydantic v2、pytest）、GitHub Actions（composite actions）、AWS CLI s3api 對 R2、TypeScript 型別生成（`packages/schema`）。

**Spec:** `docs/superpowers/specs/2026-09-26-data-pipeline-refactor-design.md`（2026-09-26 使用者核准，含 Fable 審查修訂）

## Global Constraints

- 對學校的請求量與節流不變（`client.py:76,95` 的 0.4–0.8 秒間隔不動）。
- 時間欄位只用 `observed_at`／`checked_at`／`changed_at`／`published_at`，ISO 8601 帶 `+08:00`；其他資料檔不放時間戳。
- `calendar.json` 格式不動（App 嚴格等於 `CALENDAR_SCHEMA_VERSION=1`）。
- manifest：新增 `published_at`，`generated_at` 保留且同值；`schema_version`（共用 `SCHEMA_VERSION=3`）不升。
- 品質閘門門檻 0.95（repo var `QUALITY_MIN_RATIO` 可覆寫），基準由 S3 `GetObject` 讀線上 manifest。
- 過期刪除只在 `terms/*/`、`standards/`、`calendar/` prefix 內；單 prefix 刪除 > 10% → 跳過該 prefix 刪除、照常上傳、告警；`--allow-mass-delete <prefix>` 放行。
- redline 掃描失敗 → 整次中止，不放寬。
- 公開 repo：測試 fixture 不得含學號、cunum 對應個人等個資（CLAUDE.md）。
- 每個 PR 走 worktree＋topic branch、基底 `origin/main`；合併後主 checkout `git pull --ff-only`。

## Review Focus

1. **上游回傳殘缺資料（例如學校頁面壞掉，只抓到 12 門課）**：合併進 data branch 之前就要擋下，不能等到 publish 才擋——否則 canonical 已被覆寫，隔天 diff 基準也跟著壞。期望：commit-publish job 對 catalog 做同樣的 0.95 比例檢查（對 HEAD 的課數），不過就丟棄該資料集的檔案並告警，其他資料集照常。→ Task 3 測試。
2. **某個資料集 fetch 到一半失敗**：它已寫出的部分檔案不可被合併。期望：只合併 `pipeline-result.json` 標記成功的資料集的 `writes` 檔。→ Task 3 測試。
3. **R2 listing 超過 1000 個物件**（實際約 3.3 萬、33 頁）：分頁要完整，否則會把第 1001 個以後的檔案誤判為「R2 沒有」而全部重傳，或誤判為「過期」。→ Task 2 測試（假 client 分頁）。
4. **沒有 `calendar.json` 的學期**（110-1～114-2 都沒有）在 derive 算 weekly progress：要走 `term=None` 路徑產出結果，不可報錯或產出空值。→ Task 3 測試。
5. **`season` 沒帶學期觸發**：要立刻失敗並說明，不可默默用 `current-term`（12 月時可能是錯的學期）。→ Task 5 測試（workflow 內的檢查步驟以 `act` 不可行 → 改成 `pipeline --cadence season` 在 terms 為空時 exit 2，pytest 驗證）。

---

## Task 地圖

| # | PR | 內容 | 依賴 | 產出／介面 |
|---|---|---|---|---|
| 1 | PR 1 | publish 學期範圍解析 | — | `publish.py` 以 `ntut_catalog.cli.expand_terms` 解析 `--terms` |
| 2 | PR 2 | derive／publish 分層 | 1 | `ntut_catalog derive`；`publish.py` 純上傳 |
| 3 | PR 3 | fetch 端＋登錄表＋合約 | 2 | `registry.py`、`pipeline`、`fetch_state.py`、`enrollment_store.py`、`merge.py` |
| 4 | PR 3 | 遷移＋離線驗證（**gate**） | 3 | `migrate-pipeline-v2`、`infra/verify_migration.py` |
| 5 | PR 3 | 5 個 workflow＋actions＋告警 | 3 | `.github/workflows/{daily,weekly,season,maintenance}.yml`、`.github/actions/*` |
| 6 | PR 5 | 文件 | 5 | DECISIONS／README／CLAUDE.md |
| — | — | 切換（spec §8） | 1–6 | 使用者兩個檢查點：驗證報告、孤兒檔放行 |

> 與 spec 的差異：spec §9 的 PR 3、PR 4 須同時合併，實作上合成**一個 PR**（Task 3–5 同一分支），原子性更好。

### Task 1：publish 學期範圍解析（PR 1）

- **Files:** `infra/publish.py:337`、`crawler/tests/test_publish.py`
- **內容:** `--terms` 改用 `expand_terms`（`cli.py:51`），支援 `a:b` 與逗號混用；非法格式 `ap.error`。
- **測試:** `110-1:111-1` → `["110-1","110-2","111-1"]`；`115-1,114-1:114-2` 混用；非法字串報錯。
- **驗收:** `pytest crawler/tests` 全綠；PR 合併。

### Task 2：derive／publish 分層（PR 2，可獨立合併）

- **Files:**
  - `crawler/ntut_catalog/cli.py`：新增 `derive` 子命令（`--out`）；移除 9 處 `build_v1` 呼叫（`:191,199,208,219,241,249,275,300,384`）
  - `crawler/ntut_catalog/artifacts.py`：`write_manifest` 的 `calendars` 範圍改由 canonical 決定（存在 `calendar.json` 的學期中「最新學年＋前一學年」），不讀系統時間；catalog 項目加 `count`
  - `infra/publish.py`：不呼叫 `build_v1`；全量 listing（分頁）＋MD5 比對；過期刪除＋10% 保險＋`--allow-mass-delete`；品質閘門讀線上 manifest（S3 GetObject）、門檻 0.95、移除 `--previous-counts`；manifest 上傳前寫入 `published_at`＝`generated_at`＝now；刪除清單寫 `$GITHUB_STEP_SUMMARY`
  - 現行 9 個 workflow：每支在 publish 前加 `python -m ntut_catalog derive --out data`，移除 `--previous-counts`／`--min-ratio`／`--include-details`
- **Interfaces 產出:** `derive(out_dir: Path) -> Manifest`（取代 `build_v1` 的對外名稱，內部可沿用）；`publish.py` CLI：`--bucket --out [--dry-run] [--no-skip-unchanged] [--allow-mass-delete PREFIX ...]`（`--terms`／`--all` 移除——全量比對後不需要；保留 `--terms` 只用於品質閘門要檢查哪些學期，預設＝本地 v1 中全部學期）
- **測試:** derive 確定性（兩個凍結時間 → 位元組相同）；`calendars` 不隨系統日期變；listing 分頁（假 client，2,500 物件分 3 頁，Review Focus 3）；只傳 MD5 不同者；multipart ETag 視為不同；過期刪除只在允許 prefix、永不動根；10% 觸發 → 跳過刪除、manifest 仍上傳、回傳告警旗標；`--allow-mass-delete`；閘門（有基準／無基準／0 課）。
- **驗收:** 全測試綠；本機 `derive` 兩次 `diff -r` 無差異；`publish.py --dry-run` 對真實 bucket 跑一次（需 R2 憑證；若本機無憑證則改在 PR 分支 dispatch `publish-v1` dry-run），刪除清單與上傳清單附在 PR；合併後手動 dispatch 一次 `crawl.yml` 確認排程流程正常。

### Task 3：fetch 端＋登錄表＋合約（PR 3）

- **Files（新增）:**
  - `crawler/ntut_catalog/registry.py`：`Dataset` dataclass（spec §2）、`DATASETS` 登錄表、`resolve_terms(rule, explicit) -> list[str]`
  - `crawler/ntut_catalog/fetch_state.py`：`load(path) -> FetchState`、`update(state, dataset, term, content_sha256, checked_at) -> FetchState`（hash 變才動 `changed_at`）、`content_hash(paths) -> str`
  - `crawler/ntut_catalog/enrollment_store.py`：`write_snapshot(term_dir, rows, observed_at) -> str | None`（與最後一份相同 → None）、`append_observation(term_dir, observed_at, snapshot)`、`latest(term_dir) -> tuple[list[dict], str | None]`、`history(term_dir) -> Iterator[tuple[str, list[dict]]]`
  - `crawler/ntut_catalog/merge.py`：commit-publish job 的合併邏輯 `merge_fetch_output(artifact_dir, data_dir, result) -> MergeReport`（覆寫成功資料集的 writes、快照去重、append_only 追加、fetch-state 更新、catalog 0.95 比例檢查）
  - `crawler/ntut_catalog/pipeline.py`：`run(cadence, datasets, terms, out) -> PipelineResult`，每資料集獨立 try，寫 `pipeline-result.json`
- **Files（修改）:** `cli.py`（新增 `pipeline`、`merge`；刪 `migrate`／`rederive`／`rematric`／`recategorize`／`migrate-details`／`reprocess-progress`）；`detail.py`（不寫 v1、不設 `generated_at`、不掛 progress）；`artifacts.py`（derive 時呼叫 `attach_weekly_progress` 並產出 `reports/{t}/weekly-progress.json`；enrollment 經 `enrollment_store.latest`；manifest 加 `checked_at`／`changed_at`／`details` 新鮮度）；`crawler/models.py`（`CourseDetail` 去 `generated_at`、`WeeklyProgress` 去 `parsed_at`、manifest 新欄位）；`parse_progress.py`（去 `now` 參數）；`load_term` 移到 `term_calendar.py`；刪 `migrate.py`、`rederive.py`、`rematric.py` 與 `reprocess.py` 對應函式及其測試；重生 `packages/schema` TS 型別
- **Interfaces 消費:** Task 2 的 `derive`。**產出:** 上列新模組簽名；`pipeline-result.json` 格式 `{"datasets":[{"name","term","ok","checked_at","error"}]}`。
- **測試:** fetch 冪等（fixture 上游不變 → 只有 fetch-state `checked_at` 與 observations 追加）；enrollment 去重、分鐘命名、`history` 含斷點；merge：daily＋season 以過期 checkout 先後合併不丟觀測、不重複快照、`changed_at` 只前進一次；**失敗資料集的檔案不合併**（Review Focus 2）；**catalog 課數跌破 0.95 → 丟棄 catalog 檔、其他照常、報告告警**（Review Focus 1）；**無 calendar 學期的 progress 走 `term=None`**（Review Focus 4）；`pipeline --cadence season` 無 terms → exit 2（Review Focus 5）；standards 學年規則（當前＋前 5）；web `npm run typecheck` 與 schema drift 檢查通過。
- **驗收:** crawler 全測試綠；`apps/web` typecheck／build 綠；對一份 fixture canonical 跑 `pipeline`→`merge`→`derive` 端到端。

### Task 4：遷移＋離線驗證（PR 3，**gate**）

- **Files:** `crawler/ntut_catalog/migrate_v2.py`＋CLI `migrate-pipeline-v2 --data <dir>`；`infra/verify_migration.py`；對應測試
- **內容:** spec §7 四步；enrollment 以列內 `observed_at` 命名；`verify_migration.py <old_v1> <new_v1>` 逐檔比對，只允許 §6 欄位差異，`weekly_progress` 差異列報各學期 status 計數前後對照，輸出 markdown 報告。
- **Gate:** 在本機對 `origin/data` 的完整複本跑：舊程式碼（`git worktree` 於 origin/main）`build_v1` → `old_v1/`；遷移後新程式碼 `derive` → `new_v1/`；`verify_migration.py` 通過（除允許類別外零差異）。報告附在 PR。**不寫回 origin/data**（寫回在切換時由 maintenance 做）。
- **驗收:** 測試綠；gate 報告存在且通過。

### Task 5：workflow＋共用元件＋告警（PR 3）

- **Files:** 新增 `.github/workflows/{daily,weekly,season,maintenance}.yml`、`.github/actions/{setup,commit-publish,alert}/action.yml`、`infra/pipeline_alert.py`（開／更新／關閉 issue、資料過期檢查）；刪除 8 個舊 workflow（`test.yml` 保留）
- **內容:** spec §3。fetch job 產物用 `actions/upload-artifact`（retention 7 天）；commit-publish job `concurrency: data-pipeline`、`cancel-in-progress: false`、timeout 30；順序：checkout 最新 data → `merge` → redline → pua-scan → `derive` → commit（canonical＋reports）→ push → publish。daily 最後跑 `calendar_horizon_alert.py`、`calendar_coverage_check.py`、過期檢查（daily 2 天、weekly 9 天）。`season` 的 `terms` input `required: true`。`maintenance` task：`backfill`（details 走 matrix、max-parallel 3）／`republish`／`migrate`。
- **測試:** `infra/pipeline_alert.py` 單元測試（假 `gh`）；`actionlint` 對全部 workflow 通過。
- **驗收:** actionlint 綠；在 PR 分支以 `workflow_dispatch` 對 **dry-run 模式**（`publish --dry-run`、push 到暫時分支 `data-dryrun` 而非 `data`）實跑 daily 與 weekly 各一次成功。

### Task 6：文件（PR 5）

- **Files:** `docs/DECISIONS.md`（版本規則、時間欄位命名、依頻率分、canonical 不記爬取時間）、`crawler/README.md`（登錄表、如何新增資料集、`pipeline`／`derive`／`merge` 用法）、`CLAUDE.md` 現況段、`infra/README.md`；刪除 `migrate-pipeline-v2` 子命令與 maintenance 的 `migrate` task（切換完成後）
- **驗收:** 文件中提到的路徑與指令逐一存在（grep 核對）。

### 切換（spec §8，Task 1–5 合併後）

1. `gh workflow disable` daily／weekly（新 workflow 合併前先建立為 disabled，或合併後立即 disable）與所有舊排程（舊檔在 PR 3 已刪）。
2. maintenance → `migrate`（寫回 data branch）→ 附驗證報告 → **使用者檢查點 1：看報告**。
3. maintenance → `republish` → 刪除保險預期觸發 → **使用者檢查點 2：看刪除清單、放行** → 以 `--allow-mass-delete` 重跑。
4. 手動 dispatch `daily` → 檢查 manifest 新欄位、web 規劃頁「人數更新於」、App 課綱週進度與行事曆（App 由使用者確認）。
5. 啟用 daily、weekly 排程。
6. 記錄結果到記憶與 CLAUDE.md 現況。

### 最終總審

Task 3–5 分支合併前：派一個 fresh-context 高階模型 agent 對整條分支 diff 按 spec 逐節核對（pass/fail 逐條），並特別檢查 Review Focus 五項是否都有測試。修正一批派一個 agent，附測試證據即完成。
