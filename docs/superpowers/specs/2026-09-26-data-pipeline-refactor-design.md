# 資料管線重構設計（fetch / derive / publish 分層＋依頻率分 workflow）

> 2026-09-25～26 brainstorming 定案。範圍：**資料管線全線**（`crawler/`、`infra/`、`.github/workflows/`、data branch 與 v1 產物介面）；
> `apps/web` 只在讀取端受影響時才動。空教室（NTUTBox#239）**在本重構完成後**才做，屆時只是登錄表的一筆。
> 盤點證據：近 31 天 run 紀錄（2026-08-25 → 09-25）、origin/main 65ebb56、origin/data c2eb8d9。現況圖：<https://claude.ai/artifact/Sbhzt7pwWJwMu6x3khHowb>

## 動機（實測／已確認的問題）

| 問題 | 依據 |
|---|---|
| 9 個 workflow 零共用元件：data branch checkout ×8、R2 env ×8、commit/push ×7、學期解析 ×6（4 種規則） | 逐檔比對 |
| `publish.py` 不吃 `a:b` 學期範圍（只切逗號），手動 dispatch 填範圍就發佈錯 | `infra/publish.py:337` |
| 品質閘門只在 `crawl.yml` 有效，其餘 7 條 `--previous-counts` 預設 `{}`＝永遠放行 | `infra/publish.py:329,346` |
| GitHub cron 延遲中位 2.4h（crawl 排 04:00、中位 06:26、最晚 12:05）；每小時排程 31 天只觸發 196/744 次 | run 紀錄 |
| 9/8 crawl 排隊 710 分鐘，無任何告警 | run 34167266561 |
| details 每週重爬，內容沒變也全部重傳（2,727 物件）：canonical 內嵌爬取時間 `generated_at`、`weekly_progress.parsed_at`，ETag 跳不掉；App 端 304 也全失效 | `detail.py:67`、`parse_progress.py:785`、run 35544372546 |
| `build_v1` 被 CLI 呼叫 9 處＋`publish.py` 再全量重建一次；`crawl-detail` 繞過 derive 直接寫 v1 | `cli.py`、`publish.py:343`、`detail.py:82-88` |
| weekly progress 是「課綱原文 × 行事曆 × parser 版本」的衍生物，卻存在 canonical，改了任一項要人記得手動 `reprocess-progress` | `reprocess.py`、`models.py:269` |
| enrollment「最新」靠檔名字典序取最後一個，日檔 `YYYY-MM-DD` 與時檔 `YYYY-MM-DDTHH` 混用 | `artifacts.py:142-160` |
| manifest 的 `calendars` 範圍依執行當天日期決定（非確定性） | `artifacts.py:321` |
| 一次性指令仍留在 CLI：`migrate`、`rederive`（反向 v1→canonical）、`rematric`、`recategorize`、`migrate-details` | `cli.py` |

**成功標準**：（1）新增一個資料集＝寫 fetcher＋v1 builder＋登錄表一筆，**不新增 workflow 檔**；（2）上游沒變 → data branch 除 `_meta/`、觀測紀錄外零 diff，R2 除 manifest 外零上傳；（3）catalog 上線不被 details 拖住；（4）任何資料集超過門檻沒被確認、或任何 run 失敗，都會自動開 issue；（5）web 與 App 現有行為不變。

## Non-goals

- **R2 uploader 重寫**（GPT 評估的建議）：#100 已解決主要成本（每日 publish 約 59 秒），不做。
- **details 加速（async／提高並發）**：移出關鍵路徑後 53 分鐘不影響上線，不值得增加打 APS 的風險。
- **enrollment 歷史搬到 R2/D1**：git pack 僅 12.6 MiB；本次只定讀取介面，儲存方式不變。
- **選課窗口自動判斷＋Cloudflare Cron 觸發**：本次只建 `season.yml`（手動 dispatch）；窗口解析與 Cloudflare Worker 為**後續工作，12/07（115-2 網路選課）前完成**。
- **行事曆欄位改名**：App 對 `calendar.json` 是 `CALENDAR_SCHEMA_VERSION` 嚴格相等，升版會讓舊 App 週次功能停擺；#95 已修正語意，本次不動。
- **apps/web 重構**。

## §1 三層邊界

| 層 | 職責 | 讀 | 寫 | 禁止 |
|---|---|---|---|---|
| **fetch** | 打學校／外部來源 | 網路、canonical（增量判斷） | 只寫 canonical（data branch） | 產 v1、上傳、在資料內容寫入爬取時間 |
| **derive** | canonical → v1 | canonical（含 `_meta/`） | `v1/`、`reports/` | 連網、讀系統時間 |
| **publish** | v1 → R2 | `v1/`、線上 manifest、R2 listing | R2 | 重建 v1 |

### fetch 規則

- canonical 只記內容。移除 `CourseDetail.generated_at`；canonical details **不再存 `weekly_progress`**（見 §4）；enrollment 快照的列**不再帶 `observed_at`**（時間在檔名與觀測紀錄，見 §5）。
- 每次成功 fetch 更新 `_meta/fetch-state.json`（data branch 根目錄）：

  ```json
  { "schema_version": 1,
    "datasets": {
      "catalog":   { "115-1": { "checked_at": "2026-09-26T06:26:10+08:00",
                              "changed_at": "2026-09-18T06:31:02+08:00",
                              "content_sha256": "…" } },
      "calendar":  { "_global": { … } } } }
  ```

  `content_sha256` 是該資料集該學期所有 `writes` 檔案的合併 hash；hash 不變 → 只更新 `checked_at`。無學期維度的資料集用 `_global` 鍵。
- `crawl-detail` 不再直接寫 v1。
- 一次性指令刪除：`migrate`、`rederive`、`rematric`、`recategorize`、`migrate-details` 及只被它們使用的程式（`migrate.py`、`rederive.py`、`rematric.py`、`reprocess.py` 中對應函式）與測試。`reprocess-progress` 因 §4 一併刪除。`crawl-standards` **保留**並排入 weekly。

### derive 規則

- **確定性**：同一份 canonical（含 `_meta/`）→ 逐位元組相同的 v1。唯一例外是 manifest 的 `published_at`，由 publish 在上傳前寫入（derive 產出的 manifest 不含它）。
- **全量重建**：維持每次重建全部學期（本機實測 9.6 秒、32,695 檔、219 MB），不做「只重建某學期」。理由：manifest 本來就要涵蓋全部學期；確定性保證未受影響學期的輸出不變；publish 只比對受影響範圍即可（§1 publish 規則）。省下一整套增量邏輯。
- manifest `calendars` 範圍改由 `_meta/` 內容決定（涵蓋 canonical 中存在 `calendar.json` 的學期之中「最新學年＋前一學年」），不讀系統時間。
- 產出本次 v1 檔案清單 `v1/.files.json`（不上傳），供 publish 做過期刪除。
- CLI 子命令不再呼叫 `build_v1`；derive 只有一個入口：`python -m ntut_catalog derive --out data`。

### publish 規則

- `infra/publish.py` 不再呼叫 `build_v1`；輸入是已 derive 好的 `v1/`。
- **受影響範圍**：由本次 canonical 的 git diff 推出受影響學期（`{term}/…` 路徑）與是否動到跨學期資料（`calendar/`、`standards/`、`_meta/`）。manifest 永遠在範圍內、永遠最後上傳。`maintenance` 的 `republish` 任務可指定學期或 `--all` 強制全比對。
- **ETag 比對只列受影響學期的 prefix**（`course/v1/terms/{t}/`），不再列整個 `course/`。
- **過期刪除**：受影響 prefix 內，R2 上存在但 `v1/.files.json` 沒有的物件 → 刪除。保險：（a）只在受影響 prefix 內刪；（b）單一學期刪除量 > 該學期物件數 10% → 中止整次 publish 並告警（不上傳 manifest）；（c）`--dry-run` 印出刪除清單。
- **品質閘門一律開**：基準值取線上 manifest 中該學期 catalog 的 `count`（新增欄位，見 §6）；線上無此學期 → 只檢查「不為 0」。移除 `--previous-counts`／`--min-ratio` 參數，門檻 0.9 內建。
- 修正學期範圍解析：`--terms` 走與 CLI 相同的 `expand_terms`（`cli.py:51`）。

## §2 資料集登錄表

`crawler/ntut_catalog/registry.py`，唯一宣告處：

```python
@dataclass(frozen=True)
class Dataset:
    name: str                                   # "catalog"
    cadence: Literal["daily", "weekly", "season", "manual"]
    terms: Literal["active", "current", "calendar", "none"]
    fetch: Callable[[FetchContext, str | None], None]   # (ctx, term_key)；term 無維度時為 None
    writes: tuple[str, ...]                     # data branch 相對路徑樣板，"{term}/catalog.ndjson"
    append_only: tuple[str, ...] = ()           # 由上鎖 job 以「追加」方式合併的檔案（§3）
```

| name | cadence | terms | writes |
|---|---|---|---|
| `calendar` | daily | none | `calendar/events.ndjson`、`calendar/meta.json`、`{term}/calendar.json`（多學期，由 fetcher 決定） |
| `catalog` | daily | active | `{term}/catalog.ndjson`、`{term}/classes.json`、`{term}/enrollment/*.ndjson`（append_only：`{term}/enrollment/observations.ndjson`） |
| `mprograms` | daily | active | `{term}/mprograms.json` |
| `details` | weekly | current | `{term}/details.ndjson` |
| `standards` | weekly | none | `standards/*.json` |
| `enrollment` | season | current | `{term}/enrollment/*.ndjson`（append_only 同上） |

學期規則集中實作（取代 6 份 workflow 內的 shell）：`active` = repo var `ACTIVE_TERMS`，未設則 `current`；`current` = `current-term` 查詢結果；`calendar` 由 fetcher 自決；`none` 無學期維度。

CLI：`python -m ntut_catalog pipeline --cadence daily [--datasets a,b] [--terms …] --out data`。每個資料集獨立 try，失敗記入 `pipeline-result.json`（名稱、學期、錯誤摘要），不中斷其他資料集；結束碼 = 是否有任何失敗。`git add` 範圍由登錄表 `writes` 產生，workflow 內不再手寫 glob。

## §3 Workflow（依頻率分，5 個檔）

| 檔 | 觸發 | 內容 | timeout |
|---|---|---|---|
| `daily.yml` | GitHub cron 每日＋dispatch（可帶 `datasets`／`terms`） | cadence=daily 的資料集 | fetch 60 分 |
| `weekly.yml` | GitHub cron 每週一＋dispatch | cadence=weekly | fetch 180 分 |
| `season.yml` | **僅 dispatch**（日後由 Cloudflare Cron 呼叫） | cadence=season | fetch 20 分 |
| `maintenance.yml` | 僅 dispatch，`task` ∈ `backfill`（dataset＋terms，details 走 matrix、max-parallel 3）／`republish`（terms 或 all，不 fetch） | 手動作業 | 依任務 |
| `test.yml` | push／PR | 不動 | — |

刪除：`crawl.yml`、`crawl-calendar.yml`、`crawl-details.yml`、`crawl-enrollment.yml`（2026-09-25 已 disable）、`backfill-details.yml`、`backfill-mprograms.yml`、`reprocess-progress.yml`、`publish-v1.yml`。

**依頻率分的理由**（2026-09-26 討論）：同頻率的資料集共用一次 runner／checkout／搶鎖／manifest 發佈；新增資料集不動 YAML；只剩兩條 cron 不互撞；失敗隔離靠步驟不靠檔案。代價與對策：Actions 列表看不出哪個資料集失敗 → 步驟以資料集命名＋run summary 表＋告警標資料集；同層慢者拖累他者 → 規則「同層耗時相近，慢的換層」。

### 每個 workflow 兩個 job

1. **fetch job（不上鎖）**：checkout main＋data branch → `pipeline --cadence X` → 把登錄表 `writes` 命中的變更檔、`pipeline-result.json`、本次 `fetch-state` 更新片段、`append_only` 待追加列打包成 artifact。
2. **commit-publish job（`concurrency: data-pipeline`、`cancel-in-progress: false`、timeout 30 分）**：重新 checkout **最新** data branch → 覆寫 `writes` 檔（各資料集寫入路徑互斥，直接覆寫即可）→ `append_only` 檔以追加合併 → `fetch-state.json` 依 `(dataset, term)` 鍵合併 → redline 掃描（**失敗即整次中止，不放寬**）→ pua-scan → commit（有 diff 才 commit；訊息 `data(<cadence>): <datasets> <terms>`）→ push → derive → publish（受影響範圍）。

沿用既有模式：`backfill-details.yml` 已是 matrix 爬取＋上鎖 fan-in job。

### 共用元件（`.github/actions/`）

- `setup`：checkout data branch 到 `data/canonical`、setup-python 3.12＋pip 快取、`pip install -e ./crawler`；`wrangler` 不再安裝（S3 憑證已齊，#99；wrangler fallback 保留在程式但 CI 不走）。
- `commit-publish`：上述 job 2 的全部步驟。
- `alert`：見下。

### 告警

- **run 失敗**：任一 job 失敗或 `pipeline-result.json` 有失敗 → 開／更新 label `pipeline-alert`、標題 `[pipeline] <workflow> 失敗` 的 issue（內容：失敗資料集、學期、run 連結）；下次同 workflow 全成功 → 自動留言並關閉。沿用 `infra/calendar_horizon_alert.py` 的 `gh` 作法。
- **資料太久沒確認**：`daily` 的 commit-publish job 最後檢查 `fetch-state.json`：cadence=daily 的 `checked_at` > 2 天、weekly > 9 天 → 開／更新 `[pipeline] 資料過期：<dataset>` issue。
- 既有 `calendar_horizon_alert.py`、`calendar_coverage_check.py` 保留，改由 `daily` 呼叫。

## §4 weekly progress 移到 derive

- canonical `details.ndjson` 只存學校來的課綱原文（含 `schedule` 自由文字）。
- derive 產生 `course/{id}.json` 時呼叫 `attach_weekly_progress(syllabi, term_calendar)` 即時計算；行事曆改、parser 升版 → 下次 derive 自動生效。輸出格式不變，只移除 `parsed_at`。
- `reports/{t}/weekly-progress.json` 改由 derive 產出，**仍 commit 到 data branch**（其 commit 歷史＝長期精度追蹤，`parse_progress.py:793`）；移除 `generated_at`、保留 `parser_version`；數字不變就不 commit。derive 產出 `reports/` 後由 commit-publish job 在 publish 前一併 commit。
- 刪除 `reprocess-progress` 子命令與 workflow。

## §5 enrollment：最新快照與歷史

- 快照檔：`{t}/enrollment/{YYYY-MM-DDTHHMM}.ndjson`（台北時間，精確到分），列內不含時間戳；**內容與前一份相同就不寫**。永不改寫、永不刪除（遷移時除外，見 §7）。
- 觀測紀錄：`{t}/enrollment/observations.ndjson`，每次成功爬取追加一行 `{"observed_at": "…+08:00", "snapshot": "2026-09-07T1000"}`。用途：區分「確認過、數字沒變」與「沒爬到」，圖表可重取樣到任意固定間隔（沒變 → 延用前值；無紀錄 → 斷線）。
- 讀取介面（`crawler/ntut_catalog/enrollment_store.py`）：`latest(term) -> (rows, observed_at)`、`history(term) -> Iterator[(observed_at, rows)]`。derive 與日後功能只經此介面；將來換儲存只改這裡。
- v1 `enrollment.json` 不變；其 `observed_at` = 最後一筆觀測時間（web「人數更新於」語意不變）。
- 使用者確認：選課季＋加退選以外的人數變動不重要；季外由 `daily` 順帶記錄即可。

## §6 對外合約與命名

### 時間欄位命名規則（寫入 `docs/DECISIONS.md`）

| 名稱 | 意思 |
|---|---|
| `observed_at` | 觀測當下的值（資料本身就是觀測） |
| `checked_at` | 最後一次成功向來源確認 |
| `changed_at` | 內容最後一次改變 |
| `published_at` | manifest 發佈到 R2 的時間 |

一律 ISO 8601 帶 `+08:00`。其他資料檔不放時間戳。

### 變動清單

| 產物 | 變動 | App（NTUTBox `v2` af495fd） | Web |
|---|---|---|---|
| `manifest.json` | `generated_at` → `published_at`；每個產物項目加 `checked_at`、`changed_at`；catalog 項目加 `count`；每學期加 `details: {checked_at, changed_at, count}`（無 url，純 freshness） | `CDNManifest` 只解 `schema_version`／`generated_at`(optional)／`min_app_version`／`calendars`，`generated_at` 未使用 → 安全 | `cdn-datasource.ts` 依鍵取值；**實作時驗證**新增的 `details` 鍵不影響任何遍歷 |
| `course/{id}.json` | 移除 `generated_at`、`weekly_progress.parsed_at`；該產物 `schema_version` 3 → 4 | `CourseSyllabus.generatedAt` optional 未使用；模型不解 `parsed_at` → 安全 | 重生 TS 型別 |
| `enrollment.json`、`catalog.json`、`classes.json`、`periods.json`、`mprograms.json`、`names.json`、`calendar.json`、`events.json`、`standards/` | 不動 | — | — |

- `checked_at`／`changed_at` 來源：`_meta/fetch-state.json`；產物 → 資料集對照：catalog/classes/names ← catalog、enrollment ← catalog 與 enrollment 取較新、mprograms ← mprograms、calendar ← calendar、course/* ← details。
- **版本規則**（寫入 `docs/DECISIONS.md`）：新增欄位不升版；移除／改名／改型別 → 升該產物 `schema_version`。App 目前只解碼不判斷 `schema_version`（見記憶 cdn-app-version-contract），升版為標記用途；`min_app_version` 維持 null。
- 後續：到 NTUTBox 開票清掉 App 端兩個未使用的 `generatedAt`（不擋本重構）。

## §7 一次性遷移

`python -m ntut_catalog migrate-pipeline-v2 --data data/canonical`（遷移完成、驗證後於下一個 PR 刪除）：

1. `details.ndjson`：去掉 `generated_at` 與每份 syllabus 的 `weekly_progress`。
2. enrollment：舊檔依 `git log --diff-filter=A --format=%cI -- <file>` 取首次 commit 時間 → 改名為 `YYYY-MM-DDTHHMM`；列內去掉 `observed_at`；與前一份內容相同者刪除；由改名後的序列（每個原檔各一筆觀測）重建 `observations.ndjson`。
3. `_meta/fetch-state.json`：每個 `(dataset, term)` 以該資料集 `writes` 檔最後 commit 時間初始化 `checked_at`＝`changed_at`，並算 `content_sha256`。
4. `reports/*/weekly-progress.json`：去掉 `generated_at`。

**遷移驗證**（通過才切換）：用遷移後 canonical 跑新 derive，與目前線上 v1 逐檔比對，差異必須**只**出現在 §6 列出的欄位；腳本 `infra/verify_migration.py` 輸出差異摘要附在 PR。

## §8 切換程序

1. `gh workflow disable` 所有會寫 data branch 的排程 workflow。
2. 合併 PR 3（fetch 端＋遷移腳本）與 PR 4（workflow）——兩者一起合併。
3. `maintenance` 手動跑遷移 → 驗證（§7）→ commit data branch。
4. `maintenance` → `republish --all`：一次性全量上傳（單課檔全變，約 3 萬物件，參考 #100 首次全量約 25 分鐘）。
5. 手動 dispatch `daily` → 確認：manifest 新欄位、R2 無非預期刪除、web 規劃頁「人數更新於」、App 課綱頁週進度與行事曆正常。
6. 啟用 `daily`、`weekly` 排程。`season` 維持僅 dispatch。

資料最多延後一天更新。回退：`git revert` PR 3＋4、data branch 回退到遷移前 commit、`republish --all`。

## §9 PR 拆法

| PR | 內容 | 獨立合併 |
|---|---|---|
| 1 | `publish.py` 學期範圍解析改用 `expand_terms` | 可，立即 |
| 2 | derive／publish 分層：`publish.py` 不呼叫 `build_v1`、受影響範圍、ETag 限縮 prefix、過期刪除＋保險、品質閘門改讀線上 manifest（先加 `count`）、derive 確定性（`calendars` 不讀時間、`.files.json`）；CLI 移除 9 處 `build_v1` 呼叫、改由 workflow 顯式跑 `derive` | 可，舊 workflow 補一行 `derive` 即可運作 |
| 3 | fetch 端：canonical 去時間戳、`fetch-state`、`enrollment_store`＋觀測紀錄、progress 移到 derive、登錄表＋`pipeline` 子命令、刪一次性指令、遷移與驗證腳本、manifest／course 合約變更、TS 型別重生 | 與 4 一起 |
| 4 | 5 個 workflow、`.github/actions/`、兩層告警 | 與 3 一起 |
| 5 | 文件：`DECISIONS.md`（版本規則、時間欄位命名、依頻率分）、`crawler/README.md`（登錄表、如何新增資料集）、`CLAUDE.md` 現況；刪遷移子命令 | 可 |

後續（本 spec 範圍外）：`season` 的 Cloudflare Cron 觸發＋選課窗口從行事曆解析（多段；期中撤選為「開始／結束」兩筆單日事件需配對、且不進每小時；**12/07 前**）→ 空教室 rooms → NTUTBox 清 `generatedAt`。

## 測試與驗收

- **derive 確定性**：同一 fixture canonical，以兩個不同的凍結系統時間各 derive 一次 → 兩份 `v1/` 逐位元組相同。
- **fetch 冪等**：fixture 上游不變重跑 fetch → canonical 只有 `_meta/fetch-state.json` 的 `checked_at` 與 `observations.ndjson` 追加一行有 diff。
- **enrollment_store**：去重、分鐘命名、`latest`／`history` 重建含「沒爬到」斷點的序列。
- **publish**：受影響範圍推導、prefix 限縮、過期刪除清單、10% 保險中止且不上傳 manifest、品質閘門（有基準／無基準／為 0）、學期範圍解析。
- **commit-publish 合併**：`append_only` 追加、`fetch-state` 按鍵合併，模擬兩個 run 先後進鎖不丟資料。
- **遷移**：fixture 遷移結果＋`verify_migration.py` 對線上 v1 的差異只落在 §6 欄位。
- 既有 34 個測試檔全過；刪除一次性指令的測試一併刪除。

## 風險

| 風險 | 對策 |
|---|---|
| 遷移改名依 git log 時間，極早期檔案可能是批次 commit、時間不代表實際爬取時刻 | 可接受（只影響歷史曲線精度）；驗證腳本列出同一 commit 內多檔的情況 |
| 一次性全量重傳期間 client 讀到新舊混合 | manifest 最後上傳；新舊單課檔差異只在被移除的欄位，兩端皆 optional |
| 上鎖 job 仍受「一個 group 只留一個 pending」限制 | 鎖持有時間降到 1–2 分鐘；被取消 → run 失敗告警，重跑該 workflow 即可（fetch 冪等） |
| `daily` 本身沒跑，過期檢查也不會跑 | 已知限制；日後 Cloudflare Worker 可順帶檢查線上 manifest 的 `checked_at`（與 season 觸發同一個 Worker） |
| 過期刪除誤刪 | 限受影響 prefix＋10% 保險＋dry-run；刪除清單印在 run summary |
