# infra — 部署 / CI

## 託管（決策 D6/D7）
- **爬蟲**：GitHub Actions（cron）。公開 repo 免費分鐘、長 job OK。**勿用 CF Workers 跑爬蟲**（50 子請求/CPU 上限）。
- **資料出口**：Cloudflare R2 → 自訂網域 `cdn.ntutbox.com/course/v1/…`（egress $0、邊緣快取）。commit-publish job 先 `python -m ntut_catalog derive --out data`、再 `python infra/publish.py --bucket … --out data`（S3 API 全量比對、只傳差異、刪過期檔；行為與 exit code 見 `publish.py` 檔頭）。
- **Web**：Cloudflare Workers（Static Assets），綁本 monorepo、**Root directory 設 `apps/web`**。網域 `course.ntutbox.com`。
- `api.ntutbox.com`：**預留**給未來動態後端（勿被靜態資料佔用）。

## 資料管線（v2，2026-09-26 切換）
三層（fetch → derive → publish）與依頻率分的理由見 `docs/DECISIONS.md` D11–D17；
資料集宣告在 `crawler/ntut_catalog/registry.py`（見 `crawler/README.md`）。

| workflow | 觸發 | 跑什麼 |
|---|---|---|
| `.github/workflows/daily.yml` | cron 每日 04:00（台北）＋dispatch（`datasets`／`terms`） | calendar、catalog＋人數、mprograms；另跑行事曆 horizon／coverage、資料過期與 season 排程檢查 |
| `.github/workflows/weekly.yml` | cron 每週一 05:30（台北）＋dispatch | details（課綱）、standards |
| `.github/workflows/season.yml` | **僅 dispatch**（Cloudflare Worker 依 `course/ops/season-schedule.json` 觸發，見下），`terms` 必填 | enrollment（選課季人數刷新；全校一次查、失敗退回逐系所） |
| `.github/workflows/maintenance.yml` | 僅 dispatch，`task` ∈ `backfill`／`republish` | 補爬、只 derive＋publish |
| `.github/workflows/test.yml` | push／PR | pytest＋schema 同步檢查 |

每支資料 workflow 都是 fetch job（不上鎖）→ commit-publish job（`concurrency: data-pipeline`）→ alert job，
共用 `.github/actions/{setup,commit-publish,alert}`。commit-publish 的順序：checkout 最新 data branch →
`python -m ntut_catalog merge` → `redline_scan.py`（命中即中止）→ `pua-scan` → `derive` → commit＋push → `publish.py`。

相關腳本：`publish.py`（上傳）、`data_commit.py`（commit 範圍與訊息）、`redline_scan.py`（擋個資/機密）、
`pipeline_alert.py`（`pipeline-alert` issue）、`calendar_horizon_alert.py`／`calendar_coverage_check.py`（行事曆）、
`r2-cors.json`。首次開通步驟見 `SETUP.md`。

## 維運 runbook

### 補爬：maintenance → `backfill`
Actions → **maintenance** → Run workflow：
- `task=backfill`、`dataset`＝登錄表名稱（`catalog`、`details`、`mprograms`、`standards`、`calendar`、`enrollment`）、
  `terms`＝學期（`110-1:114-2` 或 `115-1,114-2`；有學期維度的資料集必填，`calendar`／`standards` 留空）。
- details 每學期一個 matrix leg（max-parallel 3、單學期約 53 分鐘），其他資料集一個 leg；全部 fan-in 到一個上鎖的 commit-publish。
- 想先看發佈結果再動 R2：勾 `publish_dry_run`（只把上傳／刪除清單寫進 run summary；data branch 仍會 commit）。

### 只重新發佈：maintenance → `republish`
不打學校，只 derive＋publish。用在 parser／PUA／model 這類只動 derive 的變更上線、放行刪除保險、改 Cache-Control。
1. 先 `task=republish`＋`publish_dry_run=true` → 看 run summary 的上傳／刪除清單。
2. 確認後再跑一次 `task=republish`；刪除保險命中的 prefix 看過清單沒問題 → 填 `allow_mass_delete`（逗號分隔的 prefix 名稱，如 `115-1,standards,calendar`）。
3. 改的是 metadata（Cache-Control 等）、內容沒變 → 勾 `no_skip_unchanged` 全部重傳（約 3.3 萬物件、數十分鐘）。

### 選課季：season
- **觸發**：Cloudflare Worker（`ntutbox-season-scheduler`）每小時 Cron 讀 `cdn.ntutbox.com/course/ops/season-schedule.json`，
  現在這個整點在 `slots` 裡 → 以該格的 `terms` dispatch `season.yml`（D18；GitHub cron 實測 74% 被吞，不用它）。
  **排程由 Python 產、Worker 只觸發**：窗口來自週次表 `{term}/calendar.json` 的 `enrollment_windows`（行事曆解析只有
  `term_calendar.py` 一份），derive 展開成整點觸發格寫 `data/ops/season-schedule.json`，publish 傳到
  `course/ops/`（max-age=300、不參與過期刪除）。頻率：開啟後／截止前 24 小時每小時、截止時刻補一次、其餘每 3 小時
  （台北 00／03／06…）；常數在 `crawler/ntut_catalog/season_schedule.py`。
- 看排程：`curl -s https://cdn.ntutbox.com/course/ops/season-schedule.json | jq '.slots[] | select(.at >= "2026-12-07")' | head`；
  本機：`python -m ntut_catalog derive --out data && jq '.slots | length' data/ops/season-schedule.json`。
- 手動補跑仍可直接 dispatch `season.yml`，**`terms` 必填**（如 `115-2`）：選課季時 `current-term` 可能還是上一學期，默默用它會刷錯學期（pipeline 沒給 `--terms` 會 exit 2）。
- **人數來源**：先 `QueryCourse(matric=全校13碼, unit=＊)` 一次查（timeout 180 秒、最多 2 次），失敗退回逐系所；
  用了哪條記在 `pipeline-result.json` 該筆的 `enrollment_source`（`school`／`per-dept`）。連續出現 `per-dept`
  代表全校查詢變慢或被擋，人數仍正確、只是請求數回到約 60 個。
- **新學期的前置條件（自動，D19）**：season 只刷人數，需要該學期的 canonical catalog 已存在（否則該資料集失敗：`no canonical catalog — 先跑 catalog 再刷人數`）。
  daily 的 `active` 規則＝`current-term` ∪ **有選課窗口 `start ≤ 現在+30 天` 且 `end ≥ 現在` 的學期**（窗口讀 `{term}/calendar.json` 的
  `enrollment_windows`，歸屬被選的學期）。例：115-2 網路選課 12/07 開始 → 11/07 起 daily 的 catalog／mprograms 自動多爬 115-2；
  115-1 期末 season 監看 115-2；網路選課結束、學校 current-term 翻成 115-2 後只剩 115-2。**不必再手動設 `ACTIVE_TERMS`**。
  提前天數常數 `SELECTION_LEAD_DAYS = 30`（`crawler/ntut_catalog/registry.py`），可用 repo var `SELECTION_LEAD_DAYS` 覆寫。
  看 daily 這輪納入哪些學期：fetch job log 的 `upcoming selection-window terms: …`。
- **要立刻補、或自動沒生效時**（例如收到下面的「缺 catalog」告警），擇一：
  - 手動 dispatch **daily** 並帶 `terms`（例如 `115-2`；可加 `datasets=catalog`），先把該學期 catalog 建出來；
  - 或把 repo var `ACTIVE_TERMS` 設成明確清單，例如 `gh variable set ACTIVE_TERMS --body 115-1,115-2`。
    **`ACTIVE_TERMS` 有值＝明確覆寫**：完全照它、不再併 current-term 與窗口學期——事後記得清空（`gh variable set ACTIVE_TERMS --body ""`）。
- weekly 的 details 走 `current-term`；學期交界時學校預設學期何時切換要人工確認，需要時 dispatch weekly 帶 `terms`。

### 告警與 exit code
- **`pipeline-alert` issue**（`infra/pipeline_alert.py`，label `pipeline-alert`）：
  - `[pipeline] <workflow> 失敗`：任一 job 失敗、`pipeline-result.json` 有失敗的資料集、merge 丟棄或部分節點沿用（見 D16）、publish exit 3。
    內容列出資料集、學期與 run 連結。**同一 workflow 下一次全部成功 → 自動留言並關閉**；修好原因後 dispatch 同一支 workflow 即可清除（fetch 冪等）。
    maintenance 的 issue 依 task 命名（`maintenance-backfill`／`maintenance-republish`）。
  - `[pipeline] 資料過期：<dataset>`：`_meta/fetch-state.json` 中 daily 資料集 `checked_at` 超過 2 天、weekly 超過 9 天（由 daily 的 commit-publish 檢查）。
    資料恢復確認後自動關閉；daily 本身沒跑時這個檢查也不會跑（已知限制）。
  - `[pipeline] season 窗口學期缺 catalog：<term>`：season 排程在 14 天內要刷某學期、但 data branch 沒有該學期的 `catalog.ndjson`
    （season 必失敗）。正常情況 daily 30 天前就已自動納入，這是安全網：查 daily 該學期 catalog 有沒有跑、是否 0 課被 merge 丟棄，
    需要時照上面「要立刻補」處理。補上或窗口過了自動關閉（daily 檢查）。
  - daily／weekly **被 GitHub 自動停用**（公開 repo 60 天沒有 repo 活動）：season Worker 每週一台北 00:00 呼叫 enable API 保活（D19），
    最多停一週就會自動恢復。Worker log 搜 `[keepalive]`；enable 非 204 時該次 cron 標失敗（`keepalive-failed（…）`）。
    手動恢復：`gh workflow enable daily.yml && gh workflow enable weekly.yml`。
  - `[pipeline] season 未依排程執行`：12 小時內、已過 1 小時寬限的觸發格，有學期在 [at, at+1h) 沒有觀測紀錄
    （`{term}/enrollment/observations.ndjson`）。排查：`npx wrangler tail ntutbox-season-scheduler`（Worker 有沒有觸發、GitHub API 回什麼）、
    Worker 的 GitHub token 是否過期、`season` 最近的 run。最近的觸發格全部對上時自動關閉（daily 檢查）。
- **publish exit code**：`0` 成功；`1` 品質閘門擋下（某學期課數 < 線上 manifest `count` × 門檻，或為 0）→ 什麼都沒發，job 紅燈；
  `3` **刪除保險觸發**：某 prefix 待刪物件 > 該 prefix 遠端物件數 10% → 跳過該 prefix 的刪除、其餘（含 manifest）照常上線。
  commit-publish 不讓 3 紅燈、改由告警開 issue；**放行前每次 run 都會再觸發**。清除：maintenance `republish` 先 dry-run 看刪除清單，
  沒問題再以 `allow_mass_delete=<prefix>` 重跑；之後該 workflow 下一次全部成功時 issue 自動關閉。
- **pipeline 結束碼**：`0` 全部成功；`1` 部分資料集失敗（成功的照常合併上線、失敗的開 issue）；`2` 用法錯誤——與「沒產出 `pipeline-result.json`」一樣讓 fetch job 紅燈、不 commit。

### repo variables（門檻）
| 變數 | 預設 | 誰讀 | 意思 |
|---|---|---|---|
| `ACTIVE_TERMS` | 空＝`current-term` ∪ 即將選課的學期 | pipeline（`active` 學期規則） | **選填的明確覆寫**：有值時 `active` 規則的資料集（目前是 daily 的 catalog、mprograms）完全照它跑；可用 `a:b` 範圍與逗號。平常留空（D19） |
| `SELECTION_LEAD_DAYS` | `30` | pipeline（`active` 學期規則） | 選課窗口開始前幾天起把被選的學期納入 `active` |
| `QUALITY_MIN_RATIO` | `0.95` | `publish.py` 品質閘門 | 本地課數 < 線上 manifest `count` × 此值 → 不發佈（exit 1） |
| `PARTIAL_FAILURE_MAX_RATIO` | `0.05` | `ntut_catalog merge` | 失敗節點 > `node_total` × 此值 → 整筆 (資料集, 學期) 丟棄、保留 HEAD、告警 |
| `R2_BUCKET` | — | workflow → `publish.py --bucket` | 目前 `ntutbox-cdn` |

### runner
所有 workflow 釘 `runs-on: ubuntu-24.04`（D17）；映像升級排在選課季之後另開 PR 統一升，升完手動跑一次 daily／weekly 驗證。

## 待辦
- season Worker（`ntutbox-season-scheduler`，Cloudflare Cron → `workflow_dispatch`）的部署；排程與告警的 Python 端已完成（issue #111）。也可順帶檢查線上 manifest 的 `checked_at`，補「daily 沒跑就不會告警」的缺口。
- App 端省頻寬：按學期切檔、gzip/br、ETag 條件式請求、裝置快取。

> 不要把 `.env`、R2 金鑰、任何個資進 repo（公開）。憑證走 GitHub Secrets / Cloudflare 環境變數。

## season 自動觸發（Cloudflare Cron）
`infra/season-scheduler/`：cron-only Worker `ntutbox-season-scheduler`，每小時讀 CDN 的
`course/ops/season-schedule.json`，命中該整點的 slot 就 dispatch `season.yml`。無 route／Custom Domain。
部署、secret、測試與 log 見該資料夾 README（issue #111）。
