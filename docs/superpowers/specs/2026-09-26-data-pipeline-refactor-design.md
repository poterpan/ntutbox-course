# 資料管線重構設計（fetch / derive / publish 分層＋依頻率分 workflow）

> 2026-09-25～26 brainstorming 定案。範圍：**資料管線全線**（`crawler/`、`infra/`、`.github/workflows/`、data branch 與 v1 產物介面）；
> `apps/web` 只在讀取端受影響時才動。空教室（NTUTBox#239）**在本重構完成後**才做，屆時只是登錄表的一筆。
> 2026-09-26 經 Fable 審查（approve-with-changes，16 條全數採納，修訂已併入本文；審查紀要見文末）。
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

**成功標準**：（1）新增一個資料集＝寫 fetcher＋v1 builder＋登錄表一筆，**不新增 workflow 檔**；（2）上游沒變 → data branch 只有 `_meta/fetch-state.json` 的 `checked_at` 與 `observations.ndjson` 追加一行（**每次 run 固定一個小 commit，明確接受**），R2 只上傳 manifest 與 `enrollment.json`（其 `observed_at` 每次前進）；（3）catalog 上線不被 details 拖住；（4）任何資料集超過門檻沒被確認、或任何 run 失敗，都會自動開 issue；（5）web 與 App 現有行為不變。

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

  `content_sha256` 是該資料集該學期「內容檔」的合併 hash（catalog 只算 `catalog.ndjson`＋`classes.json`，**不含** enrollment；enrollment 另為 `enrollment` 鍵，`changed_at`＝最新快照時間）；hash 不變 → 只更新 `checked_at`。無學期維度的資料集用 `_global` 鍵。
  **所有「有沒有變」的判斷（`content_sha256`、`changed_at`、enrollment 快照去重）都在上鎖的 commit-publish job 內、對最新 data branch 計算**；fetch job 只交出檔案與 `checked_at`（§3）。
- `crawl-detail` 不再直接寫 v1。
- 一次性指令刪除：`migrate`、`rederive`、`rematric`、`recategorize`、`migrate-details` 及只被它們使用的程式（`migrate.py`、`rederive.py`、`rematric.py`、`reprocess.py` 中對應函式）與測試。`reprocess-progress` 因 §4 一併刪除。**保留** `load_term`（`reprocess.py:45`，derive 需要），移到 `term_calendar.py`。`crawl-standards` **保留**並排入 weekly。

### derive 規則

- **確定性**：同一份 canonical（含 `_meta/`）→ 逐位元組相同的 v1。唯一例外是 manifest 的 `published_at`／`generated_at`，由 publish 在上傳前寫入（derive 產出的 manifest 不含它）。parse_progress 的 `now` 只用於 `parsed_at`（`parse_progress.py:653,682,785`），移除後即確定性。
- **全量重建**：維持每次重建全部學期（本機實測 9.6 秒、32,695 檔、219 MB；progress 移入後實測 2,304 份課綱 0.7 秒，全量約 3 萬份估 +9 秒），不做「只重建某學期」、不做 progress 快取。
- manifest `calendars` 範圍改由 `_meta/` 內容決定（涵蓋 canonical 中存在 `calendar.json` 的學期之中「最新學年＋前一學年」），不讀系統時間。
- CLI 子命令不再呼叫 `build_v1`；derive 只有一個入口：`python -m ntut_catalog derive --out data`。

### publish 規則

- `infra/publish.py` 不再呼叫 `build_v1`；輸入是已 derive 好的 `v1/`。
- **一律全量比對**（Fable P1-1）：列出 `course/v1/` 下全部物件（約 33 頁 listing）與本地 `v1/` 逐檔 MD5 比對，只上傳不同者。不做「由 git diff 推受影響學期」——parser／PUA／model 這類只動 derive 的變更沒有 canonical diff，會讓 R2 靜默過期；而全量比對只需數秒。manifest 永遠最後上傳。`publish --no-skip-unchanged` 取代舊的 republish 需求。
- **過期刪除**：在 `terms/*/`、`standards/`、`calendar/` 這些 prefix 內（**永不動 v1 根目錄**），R2 有而本地 `v1/` 沒有的物件 → 刪除。保險：單一 prefix（每學期一個）刪除量 > 該 prefix 物件數 10% → **跳過該 prefix 的刪除、其餘照常上傳（含 manifest）並開告警**，不擋當天資料上線（Fable P1-2）；`--dry-run` 印刪除清單；刪除清單寫進 run summary。首次執行預期會命中累積的孤兒檔（`artifacts.py:318`），屆時人工看告警後以 `--allow-mass-delete <term>` 放行。
- **品質閘門一律開**：基準值取**線上** manifest 中該學期 catalog 的 `count`（新增欄位，見 §6），以 S3 `GetObject` 直讀 bucket（不走 CDN，避免 max-age=300 快取）；線上無此學期或尚無 `count` → 只檢查「不為 0」。門檻 **0.95**（沿用現行 `publish.py:328`；repo var `QUALITY_MIN_RATIO` 可覆寫）。移除 `--previous-counts` 參數。
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
| `standards` | weekly | none | `standards/*.json`（入學年＝當前學年與前 5 學年；`crawl-standards` 需 `--years`，`cli.py:117`） |
| `enrollment` | season | current | `{term}/enrollment/*.ndjson`（append_only 同上） |

學期規則集中實作（取代 6 份 workflow 內的 shell）：`active` = repo var `ACTIVE_TERMS`，未設則 `current`；`current` = `current-term` 查詢結果（＝QueryCurrPage 預設學期，`client.py:145`；**12 月 115-2 選課期間它可能仍是 115-1**，故 `season` dispatch 的 `terms` 為**必填**，weekly details 在學期交界需人工確認預設何時切換——與現行 `crawl-enrollment.yml:88` 行為相同，非新問題）；`calendar` 由 fetcher 自決；`none` 無學期維度。

CLI：`python -m ntut_catalog pipeline --cadence daily [--datasets a,b] [--terms …] --out data`。每個資料集獨立 try，失敗記入 `pipeline-result.json`（名稱、學期、錯誤摘要），不中斷其他資料集；結束碼 = 是否有任何失敗。`git add` 範圍由登錄表 `writes` 產生，workflow 內不再手寫 glob。

## §3 Workflow（依頻率分，5 個檔）

| 檔 | 觸發 | 內容 | timeout |
|---|---|---|---|
| `daily.yml` | GitHub cron 每日＋dispatch（可帶 `datasets`／`terms`） | cadence=daily 的資料集 | fetch 60 分 |
| `weekly.yml` | GitHub cron 每週一＋dispatch | cadence=weekly | fetch 180 分 |
| `season.yml` | **僅 dispatch**（日後由 Cloudflare Cron 呼叫） | cadence=season | fetch 20 分 |
| `maintenance.yml` | 僅 dispatch，`task` ∈ `backfill`（dataset＋terms，details 走 matrix、max-parallel 3）／`republish`（不 fetch，derive＋`publish --no-skip-unchanged`）／`migrate`（§7，**暫時性**，PR 5 移除） | 手動作業 | 依任務 |
| `test.yml` | push／PR | 不動 | — |

刪除：`crawl.yml`、`crawl-calendar.yml`、`crawl-details.yml`、`crawl-enrollment.yml`（2026-09-25 已 disable）、`backfill-details.yml`、`backfill-mprograms.yml`、`reprocess-progress.yml`、`publish-v1.yml`。

**依頻率分的理由**（2026-09-26 討論）：同頻率的資料集共用一次 runner／checkout／搶鎖／manifest 發佈；新增資料集不動 YAML；只剩兩條 cron 不互撞；失敗隔離靠步驟不靠檔案。代價與對策：Actions 列表看不出哪個資料集失敗 → 步驟以資料集命名＋run summary 表＋告警標資料集；同層慢者拖累他者 → 規則「同層耗時相近，慢的換層」。

### 每個 workflow 兩個 job

1. **fetch job（不上鎖）**：checkout main＋data branch → `pipeline --cadence X` → 把登錄表 `writes` 命中的檔案、`pipeline-result.json`（含各資料集 `checked_at`）、`append_only` 待追加列打包成 artifact。**不在這裡判斷內容是否改變**（這份 checkout 可能已過期）。
2. **commit-publish job（`concurrency: data-pipeline`、`cancel-in-progress: false`、timeout 30 分）**，順序（Fable P1-3）：重新 checkout **最新** data branch → 合併：覆寫 `writes` 檔；enrollment 快照與最新 HEAD 的最後一份比對、相同就丟棄（daily 與 season 會同時寫 `{term}/enrollment/`，檔名唯一不衝突，去重在此處做）；**只合併 `pipeline-result.json` 標記成功的資料集**（失敗者已寫出的部分檔案丟棄）；catalog 課數 < HEAD 課數 × 0.95 → 丟棄該學期 catalog 檔並告警、其他資料集照常（上游殘缺不可覆寫 canonical，否則隔天的比較基準也壞掉）；`append_only` 追加；對最新 HEAD 計算 `content_sha256`／`changed_at` 並依 `(dataset, term)` 鍵更新 `fetch-state.json` → redline 掃描（**失敗即整次中止，不放寬**）→ pua-scan → **derive**（產出 `v1/` 與 `reports/`）→ commit（canonical＋`reports/`；訊息 `data(<cadence>): <datasets> <terms>`）→ push → publish。

沿用既有模式：`backfill-details.yml` 已是 matrix 爬取＋上鎖 fan-in job。

### 節點失敗的處理

catalog／standards／mprograms／details 都是逐「節點」打上游（一個請求＝一個節點）。單一節點在 client 重試 5 次後仍失敗時，fetcher 照舊跳過續跑（不讓一個節點拖垮整輪、請求量與節流不變），但**必須回報**——否則殘缺結果被當成成功、覆寫完整的 canonical 並發佈，且不會告警（實例：一個系所的 QueryCourse 失敗 → 該系課程整段消失，只占全校 2–5%，0.95 課數檢查抓不到）。

- **回報**：`pipeline-result.json` 每筆加 `failed_nodes`（節點鍵）與 `node_total`（實際嘗試的節點數；非逐節點的資料集為 `null`）。節點鍵：catalog `{"dept"}`（Subj -3）／`{"unit"}`（系所 QueryCourse）／`{"matric"}`（學制查詢）；standards `{"year","matric","division"}`（-4）或 `{"year","matric"}`（-3，整個學制沒展開）；mprograms `{"program"}`（Cprog -4）；details `{"offering_id"}`（該課的 Curr 或任一份大綱失敗即算）。
- **merge（鎖內、對最新 HEAD）**：
  - 失敗節點 > `node_total` × **5%**（env `PARTIAL_FAILURE_MAX_RATIO` 可覆寫；`node_total` 缺或為 0 也算）→ 整筆 (資料集, 學期) 丟棄、保留 HEAD、告警，不分資料集。
  - **catalog**：任何失敗節點 → 丟棄該學期 catalog 檔**與同次人數快照**（保留 HEAD）並告警。不做節點拼接。
  - **standards／mprograms／details**：逐節點從 HEAD 沿用前一版拼進新檔——standards 以 `standards/{year}.json` 內的 (matric, division) 為鍵（-3 失敗沿用該學制全部系所）、mprograms 以 `{term}/mprograms.json` 的學程 code 為鍵（失敗的只有 Cprog -4，故只沿用 `courses`／`rules_text`，`offering_ids` 用本次成功抓到的）、details 以 `{term}/details.ndjson` 的 offering_id 為鍵（整行換成 HEAD 那一行）。HEAD 也沒有 → standards 該系所不出現、mprograms 保留本次降級版本（`courses=[]`）、details 該行不寫，並在告警列為缺漏。輸出順序與 fetcher 相同（standards 依 HEAD 相對位置插回），除失敗節點外都沒變時與 HEAD 逐位元組相同。發 **warning** 等級告警（列出沿用與缺漏的節點）。
- **fetch-state**：丟棄者不動；沿用者照常更新 `checked_at`（資料集確實確認過），MergeReport 的 `applied` 項目標 `partial: true`、`failed_nodes: <數量>`，另有 `partial: [{name, term, failed, node_total, carried_forward, missing}]`。
- **告警**：warning 與丟棄一樣列進 run issue（`[pipeline] <workflow> 失敗`）與 run summary 表（另列「部分節點失敗」表）——沿用的舊資料要有人知道；下一次全部成功即自動關閉。

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
- `reports/{t}/weekly-progress.json` 改由 derive 產出，**仍 commit 到 data branch**（其 commit 歷史＝長期精度追蹤，`parse_progress.py:793`）；移除 `generated_at`、保留 `parser_version`；數字不變就不 commit。`reports/` 由 commit-publish job 在 derive 之後、push 之前一併 commit（§3 job 2 順序）。
- 刪除 `reprocess-progress` 子命令與 workflow。

## §5 enrollment：最新快照與歷史

- 快照檔：`{t}/enrollment/{YYYY-MM-DDTHHMM}.ndjson`（台北時間，精確到分），列內不含時間戳；**內容與前一份相同就不寫**。永不改寫、永不刪除（遷移時除外，見 §7）。
- 觀測紀錄：`{t}/enrollment/observations.ndjson`，每次成功爬取追加一行 `{"observed_at": "…+08:00", "snapshot": "2026-09-07T1000"}`。用途：區分「確認過、數字沒變」與「沒爬到」，圖表可重取樣到任意固定間隔（沒變 → 延用前值；無紀錄 → 斷線）。
- 讀取介面（`crawler/ntut_catalog/enrollment_store.py`）：`latest(term) -> (rows, observed_at)`、`history(term) -> Iterator[(observed_at, rows)]`。derive 與日後功能只經此介面；將來換儲存只改這裡。
- v1 `enrollment.json` 形狀不變：頂層 `observed_at` 與每列 `observed_at`（`artifacts.py:151-156` 目前從快照列複製）都由 derive 填入**最後一筆觀測時間**（web「人數更新於」語意不變）。
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

| 產物 | 變動 | App（NTUTBox `v2` af495fd，Fable 已核對解碼器） | Web |
|---|---|---|---|
| `manifest.json` | **新增** `published_at`，`generated_at` **保留且同值**（改名會觸發共用 `SCHEMA_VERSION` 升版連帶波及 catalog 等，`models.py:27`；`generated_at` 留待 App 清理後再移除）；每個產物項目加 `checked_at`、`changed_at`；catalog 項目加 `count`；每學期加 `details: {checked_at, changed_at, count}`（無 url，純 freshness） | `CDNManifest` 只解 `schema_version`／`generated_at`(optional)／`min_app_version`／`calendars`，`generated_at` 未使用 → 安全 | 只做 `Object.keys(manifest.terms)`（`worker/index.ts:105`、`use-latest-term.ts:13`、`TermSwitcher.tsx:18`、`build-catalog.ts:48`），無 runtime `schema_version` 檢查 → 新增鍵安全 |
| `course/{id}.json` | 移除 `generated_at`、`weekly_progress.parsed_at`（**此產物沒有 `schema_version` 欄位**，`models.py:335-345`；App `CourseSyllabus.swift:9` 亦註明，故不升版） | `CourseSyllabusDocument.generatedAt` optional 未使用（`:297`）；`WeeklyProgressWire` 不解 `parsed_at`（`:242-254`）；JSONDecoder 忽略未知鍵 → 安全 | 重生 TS 型別 |
| `enrollment.json`、`catalog.json`、`classes.json`、`periods.json`、`mprograms.json`、`names.json`、`calendar.json`、`events.json`、`standards/` | 不動 | — | — |

- `checked_at`／`changed_at` 來源：`_meta/fetch-state.json`；產物 → 資料集對照：catalog/classes/names ← catalog、enrollment ← catalog 與 enrollment 取較新、mprograms ← mprograms、calendar ← calendar、course/* ← details。
- **版本規則**（寫入 `docs/DECISIONS.md`）：新增欄位不升版；移除／改名／改型別 → 升該產物 `schema_version`（沒有此欄位的產物，如 `course/{id}.json`，只能做向後相容的移除 optional 欄位）。注意 `SCHEMA_VERSION` 目前是全產物共用常數，改名優先以「新增＋保留舊名」處理。App 目前只解碼不判斷 `schema_version`（見記憶 cdn-app-version-contract），升版為標記用途；`min_app_version` 維持 null。
- 後續：到 NTUTBox 開票清掉 App 端兩個未使用的 `generatedAt`（不擋本重構）。

## §7 一次性遷移

`python -m ntut_catalog migrate-pipeline-v2 --data data/canonical`（遷移完成、驗證後於下一個 PR 刪除）：

1. `details.ndjson`：去掉 `generated_at` 與每份 syllabus 的 `weekly_progress`。
2. enrollment：每個舊檔的列本來就帶 `observed_at`（`artifacts.py:100`），**以列內值**決定新檔名 `YYYY-MM-DDTHHMM`（不用 git log：日檔是原地覆寫，`artifacts.py:92`，首次 commit 時間不代表現存內容）；列內去掉 `observed_at`；與前一份內容相同者刪除；每個原檔各一筆觀測重建 `observations.ndjson`。
3. `_meta/fetch-state.json`：每個 `(dataset, term)` 以該資料集 `writes` 檔最後 commit 時間初始化 `checked_at`＝`changed_at`，並算 `content_sha256`。
4. `reports/*/weekly-progress.json`：去掉 `generated_at`。

**遷移驗證**（通過才切換，**離線**、不下載 R2）：以舊版程式碼對遷移前 canonical 跑 `build_v1`、以新版程式碼對遷移後 canonical 跑 `derive`，兩份 `v1/` 本機逐檔比對。**閘門**：除下列兩類外不得有差異——（a）§6 列出的欄位；（b）`weekly_progress` 內容差異：derive 用現行 parser 重算，未重跑過的學期會反映 2026-09-18 的規則改動（`parse_progress.py:660-669`，版號仍 `progress/1.0.0`），**允許但必須列報**（各學期 status 計數前後對照）。腳本 `infra/verify_migration.py` 輸出差異摘要附在 PR。

## §8 切換程序

1. `gh workflow disable` 所有會寫 data branch 的排程 workflow。
2. 合併 PR 3（fetch 端＋遷移腳本）與 PR 4（workflow）——兩者一起合併。PR 3 之後 `CourseDetail`（`extra="forbid"`，`models.py:337`）會拒絕舊資料的 `generated_at`，**遷移前任何 derive 都會失敗**，所以第 1 步停排程是必要條件。
3. `maintenance` 手動跑遷移 → 驗證（§7）→ commit data branch。
4. `maintenance` → `republish`：一次性重傳（**不需重爬任何資料**；單課檔全變約 3 萬物件，其餘產物 ETag 相同跳過；參考 #100 首次全量 1.9 萬物件 24 分鐘，估 **35–40 分鐘**；刪除保險預期觸發，人工放行孤兒檔）。
5. 手動 dispatch `daily` → 確認：manifest 新欄位、R2 無非預期刪除、web 規劃頁「人數更新於」、App 課綱頁週進度與行事曆正常。
6. 啟用 `daily`、`weekly` 排程。`season` 維持僅 dispatch。

切換當天合計約 1.5 小時（遷移 5 分、驗證 5 分、重傳 35–40 分、手動 daily 12 分、web／App 檢查 15 分）；資料最多延後一天更新。回退：`git revert` PR 3＋4、data branch **force-push** 回遷移前 commit（會遺失其間的觀測紀錄）、舊流程全量 publish。

## §9 PR 拆法

| PR | 內容 | 獨立合併 |
|---|---|---|
| 1 | `publish.py` 學期範圍解析改用 `expand_terms` | 可，立即 |
| 2 | derive／publish 分層：`publish.py` 不呼叫 `build_v1`、全量比對、過期刪除＋保險、品質閘門改讀線上 manifest（先加 `count`、門檻 0.95）、derive 確定性（`calendars` 不讀時間）；CLI 移除 9 處 `build_v1` 呼叫、新增 `derive` 子命令 | 可。舊 workflow 需同步：每支加 `derive` 步驟，並移除 `--previous-counts`／`--min-ratio`／`--include-details`（`crawl.yml:158-159`、`crawl-details.yml:126` 等） |
| 3 | fetch 端：canonical 去時間戳、`fetch-state`、`enrollment_store`＋觀測紀錄、progress 移到 derive、登錄表＋`pipeline` 子命令、刪一次性指令、遷移與驗證腳本、manifest／course 合約變更、TS 型別重生 | 與 4 一起 |
| 4 | 5 個 workflow、`.github/actions/`、兩層告警 | 與 3 一起 |
| 5 | 文件：`DECISIONS.md`（版本規則、時間欄位命名、依頻率分）、`crawler/README.md`（登錄表、如何新增資料集）、`CLAUDE.md` 現況；刪遷移子命令 | 可 |

後續（本 spec 範圍外）：`season` 的 Cloudflare Cron 觸發＋選課窗口從行事曆解析（多段；期中撤選為「開始／結束」兩筆單日事件需配對、且不進每小時；**12/07 前**）→ 空教室 rooms → NTUTBox 清 `generatedAt`。

## 測試與驗收

- **derive 確定性**：同一 fixture canonical，以兩個不同的凍結系統時間各 derive 一次 → 兩份 `v1/` 逐位元組相同。
- **fetch 冪等**：fixture 上游不變重跑 fetch → canonical 只有 `_meta/fetch-state.json` 的 `checked_at` 與 `observations.ndjson` 追加一行有 diff。
- **enrollment_store**：去重、分鐘命名、`latest`／`history` 重建含「沒爬到」斷點的序列。
- **publish**：全量比對只傳差異、過期刪除清單（不碰根目錄）、10% 保險觸發時跳過該 prefix 刪除但照常上傳 manifest 並告警、品質閘門（有基準／無基準／為 0，基準由 S3 讀取）、學期範圍解析。
- **commit-publish 合併**：`append_only` 追加、`fetch-state` 按鍵合併、enrollment 快照對最新 HEAD 去重，模擬 daily 與 season 以過期 checkout 先後進鎖：不丟觀測、不產生重複快照、`changed_at` 只前進一次。
- **遷移**：fixture 遷移結果＋`verify_migration.py` 對線上 v1 的差異只落在 §6 欄位。
- 既有 34 個測試檔全過；刪除一次性指令的測試一併刪除。

## 風險

| 風險 | 對策 |
|---|---|
| 一次性全量重傳期間 client 讀到新舊混合 | manifest 最後上傳；新舊單課檔差異只在被移除的欄位，兩端皆 optional |
| 上鎖 job 仍受「一個 group 只留一個 pending」限制 | 鎖持有時間降到 1–2 分鐘；被取消 → run 失敗告警，重跑該 workflow 即可（fetch 冪等） |
| `daily` 本身沒跑，過期檢查也不會跑 | 已知限制；日後 Cloudflare Worker 可順帶檢查線上 manifest 的 `checked_at`（與 season 觸發同一個 Worker） |
| 過期刪除誤刪 | 只在 `terms/*/`、`standards/`、`calendar/` 內刪、永不動根目錄＋每 prefix 10% 保險（觸發即跳過刪除並告警）＋dry-run；刪除清單印在 run summary |

## 附錄：Fable 審查紀要（2026-09-26）

結論 approve-with-changes。採納並已併入：P1-1 publish 改一律全量比對（去掉 git diff 推範圍）；P1-2 刪除保險觸發時不擋上線；P1-3 commit-publish 順序改為 derive 在 commit 前；P1-4 內容是否改變一律在鎖內對最新 HEAD 判斷；P1-5 catalog hash 不含 enrollment；P1-6 遷移改用列內 `observed_at`；P1-7 course 檔無 `schema_version`、manifest 改為新增 `published_at` 保留 `generated_at`；P2：progress 差異允許但列報、derive 耗時實測、成功標準 2 修正（每次 run 一個小 commit）、standards 學年規則、`current` 學期交界風險與 season 必填 terms、maintenance 加 `migrate`、保留 `load_term`、enrollment 每列 `observed_at` 由 derive 填、閘門維持 0.95 且基準走 S3、PR 2 對舊 workflow 的同步修改、回退需 force-push；YAGNI 刪 `.files.json`。
