# ntutbox-season-scheduler

選課季人數刷新（`season.yml`）的準時觸發器，issue #111 的 Cloudflare 端。

## 做什麼

GitHub Actions 的 cron 不可靠（實測每小時排程約 74% 被吞、每日排程延遲中位 2.4 小時），
所以改由 Cloudflare Cron Trigger 每小時整點（`0 * * * *`，UTC；台北 UTC+8 整點對齊）醒來：

1. 讀 `https://cdn.ntutbox.com/course/ops/season-schedule.json`（Python 端從行事曆解析、發佈到 R2）。
2. 把 `scheduledTime`（原定時間，Cloudflare 晚幾分鐘執行也不影響）截到整點，找 `at` 為同一時刻的 slot
   （以 instant 比較，`2026-10-05T00:00:00+08:00` ＝ `2026-10-04T16:00Z`）。
3. 命中 → `POST /repos/poterpan/ntutbox-course/actions/workflows/season.yml/dispatches`，
   body `{"ref":"main","inputs":{"terms": slot.terms}}`（逗號分隔的 terms 原樣傳）。期待 204。

窗口與頻率全部由排程表決定，worker 不懂行事曆。排程表格式：

```json
{"schema_version":1,"calendar_sha256":"…","slots":[
  {"at":"2026-10-05T00:00:00+08:00","terms":"115-1","windows":["期中撤選"],"reason":"open-burst"}
]}
```

| 狀況 | 行為 |
|---|---|
| 排程表 404（尚未發佈） | log 一行、不觸發，視為正常 |
| 排程表其他 HTTP 錯誤／非 JSON／格式不符 | log error、不觸發、該次 cron 標失敗 |
| 該整點無 slot | log 一行、不觸發 |
| GitHub 5xx 或網路錯誤 | 重試一次 |
| GitHub 非 204 | log status＋body、該次 cron 標失敗 |
| 缺 `GITHUB_TOKEN` | log error、不發任何請求、該次 cron 標失敗 |

## 與 zone 的關係

**純 cron worker：沒有 route、沒有 Custom Domain、`workers_dev = false`、`preview_urls = false`**，
部署不會碰 `ntutbox.com` zone 的路由（zone 拓撲見 `ntutbox-edge/docs/zone-topology.md`）。
也沒有 `fetch` handler。本資料夾在 `apps/web` 之外，不影響 `ntutbox-course-web` 的 Workers Builds
（Root directory＝`apps/web`）；本 worker 目前不接 Workers Builds，手動部署。

## 部署

以下都在本資料夾（`infra/season-scheduler/`）執行：

```sh
npm ci
npm test
npx wrangler deploy
```

設定 secret（部署後、或第一次部署前皆可；值不進 repo）：

```sh
npx wrangler secret put GITHUB_TOKEN
```

token 用 **fine-grained PAT**：Repository access 只選 `poterpan/ntutbox-course`，
Permissions → Repository → **Actions: Read and write**（其餘不給）。注意 PAT 有到期日，到期前要換。

## 手動測試

```sh
npx wrangler dev --test-scheduled            # 本機跑；要測 dispatch 可加 --var GITHUB_TOKEN:<token>
curl "http://localhost:8787/__scheduled?cron=0+*+*+*+*"
```

本機觸發的 `scheduledTime` 是當下時間，所以只有當下這個整點剛好有 slot 才會 dispatch。
正式環境也可在 dashboard（Workers & Pages → ntutbox-season-scheduler → Settings → Trigger Events）看 Cron Events。

## 看 log

```sh
npx wrangler tail ntutbox-season-scheduler
```

`[observability] enabled = true`，歷史 log 也可在 dashboard 的 Observability 查。

## 開發

`src/scheduler.ts` 是全部邏輯；`src/index.ts` 只放 handler（workerd 會把 entry module 的具名匯出
當成 handler，匯出常數會讓 runtime 啟動失敗）。測試（vitest，mock fetch）在 `test/`，
`npm run typecheck` 跑 tsc。CI 由 `.github/workflows/test.yml` 的 `season-scheduler` job 跑。
