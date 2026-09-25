# infra — 上線設定（go-live runbook）

> 程式碼/設定已就緒（見 `.github/workflows/{daily,weekly,season,maintenance}.yml`、`publish.py`、`redline_scan.py`、`r2-cors.json`）。
> 本檔是**對外資源建立**步驟——需在 Cloudflare/GitHub 實際開通。每一步做完再做下一步。
> 設計依據：`docs/superpowers/specs/2026-06-13-infra-data-pipeline-design.md`。

## 前置
- `gh` 已登入（`gh auth status`）、`wrangler` 已登入（`wrangler whoami`）。
- 網域 `ntutbox.com` 已在 Cloudflare（DNS 可加 `cdn` 子網域）。
- 本地已完成遷移：`data` branch 有 11 學期 canonical、`main` 為純 code。

## 0. ⚠️ 公開前必做：清掉 main 歷史中的 data/canonical blobs
canonical 已搬到 orphan `data` branch，但 **main 的歷史仍殘留 ~35MB+ 的 data/canonical blobs**（P0/rederive/migrate 三個 commit）。公開前用 git-filter-repo 從 main 歷史移除（只影響 main；`data` branch 的 canonical 在 root path、不受影響）。
```bash
# 已備份：/tmp/ntutbox-pre-data-split.bundle 與 backup/pre-data-split branch
git filter-repo --path data/canonical --invert-paths --force --refs main
# 驗證：main 歷史不再含 canonical（應為 0）
git rev-list main --objects | grep -c 'data/canonical' || true
```
> filter-repo 會改寫 main 所有 commit SHA（repo 尚未 push，安全）。`data` branch 不動。

## 1. GitHub repo（public）
```bash
# 在 repo 根目錄
gh repo create ntutbox-course --public --source=. --remote=origin --description "北科盒子 排課系統"
git push -u origin main
git push origin data          # 推 orphan data branch（canonical 時序）
```
> ⚠️ 公開前確認：`git ls-files | grep -i -E 'env|secret|key'` 應為空；`python infra/redline_scan.py data/canonical` 乾淨（CI 也會擋）。

## 2. Cloudflare R2 bucket + 自訂網域 + CORS
```bash
wrangler r2 bucket create ntutbox-cdn
# 綁自訂網域（dashboard：R2 → ntutbox-cdn → Settings → Custom Domains → 加 cdn.ntutbox.com）
#   或 API：見 https://developers.cloudflare.com/r2/buckets/public-buckets/#custom-domains
# 套 CORS（允許 course.ntutbox.com 與本機 dev）
wrangler r2 bucket cors set ntutbox-cdn --file infra/r2-cors.json
```
物件 key 前綴 `course/v1/...` → 對外即 `https://cdn.ntutbox.com/course/v1/...`。

## 3. Cloudflare API token（給 GitHub Actions）
Dashboard → My Profile → API Tokens → Create Token：
- 權限：**Account → Workers R2 Storage → Edit**（限 `ntutbox-cdn` 所在帳號）。
- 記下 token 與 **Account ID**（R2 概覽頁）。

## 4. GitHub secrets / variables
```bash
gh secret set CLOUDFLARE_API_TOKEN          # 貼上 token
gh secret set CLOUDFLARE_ACCOUNT_ID         # 貼上 account id
gh secret set R2_S3_ACCESS_KEY_ID           # 同一組 R2 API Token 的 Access Key ID（對照表 docs/ARCHITECTURE.md §6）
gh secret set R2_S3_SECRET_ACCESS_KEY       # 同一組 token 的 Secret Access Key（只顯示一次）
gh variable set R2_BUCKET --body ntutbox-cdn
gh variable set ACTIVE_TERMS --body ""      # 留空＝daily 自動偵測當前學期；新學期選課前要設成含新學期，見 infra/README.md runbook
gh variable set QUALITY_MIN_RATIO --body 0.95
# 選填：單筆資料集節點失敗占比上限（merge；未設＝0.05，見 spec §3「節點失敗的處理」）
# gh variable set PARTIAL_FAILURE_MAX_RATIO --body 0.05
```

## 5. 首次全量發佈（一次性）
```bash
# 需 R2 S3 憑證（R2_S3_ACCESS_KEY_ID／R2_S3_SECRET_ACCESS_KEY、CLOUDFLARE_ACCOUNT_ID）
python -m ntut_catalog derive --out data
python infra/publish.py --bucket ntutbox-cdn --out data --dry-run   # 先看上傳／刪除清單
python infra/publish.py --bucket ntutbox-cdn --out data
```

## 6. 驗證
```bash
curl -I https://cdn.ntutbox.com/course/v1/manifest.json     # 200 + cache-control: max-age=300
curl -I https://cdn.ntutbox.com/course/v1/terms/115-1/catalog.json   # 200 + max-age=3600 + content-encoding
curl -s -H "Origin: https://course.ntutbox.com" -I https://cdn.ntutbox.com/course/v1/manifest.json | grep -i access-control
```

## 7. 啟用排程
- `daily.yml`（每日 04:00 台北）與 `weekly.yml`（每週一 05:30 台北）已含 `schedule`；`season.yml`、`maintenance.yml` 僅 dispatch。
- 先手動跑一次驗證：GitHub → Actions → **daily** → Run workflow（`terms` 留空＝登錄表規則）。
  - 確認：`data` branch 出現 `data(daily): …` commit（上游沒變時只有 `_meta/fetch-state.json` 與 `observations.ndjson` 一行）；R2 manifest 的 `published_at` 更新；沒有開 `pipeline-alert` issue。
- 排程被停用過（如切換期間）→ `gh workflow enable daily.yml`、`gh workflow enable weekly.yml`。

## 8. GA4 成效分析（排課站；opt-in）
`apps/web` 的 GA4 埋點靠 **build-time** env 開關，全部缺席 → 完全 no-op（不載入任何 Google 資源）。
`wrangler.jsonc` 的 `vars` **進不了 client bundle**，必須設在 Cloudflare dashboard →
Workers（`ntutbox-course-web`）→ Settings → **Build** → Build variables（Production／Preview 各設一份）：

| 變數 | 值 | 說明 |
|---|---|---|
| `NEXT_PUBLIC_GA_MEASUREMENT_ID` | `G-XXXXXXXXXX` | 與官網共用同一組（兩站同屬 ntutbox.com，共用 GA client/session） |
| `NEXT_PUBLIC_GA_ENABLED` | `true` | 缺席或非 `true` → 全站 no-op |
| `NEXT_PUBLIC_GA_DEBUG` | （不設） | 只在要用**另一組 debug stream** 於 localhost/preview 驗 DebugView 時設 `true`（會放寬 host 閘門，**別配 production ID**） |

- production GA 只在 `course.ntutbox.com` / `ntutbox.com` / `www.ntutbox.com` 送出（host allowlist）。
- 同意狀態走第一方 cookie `ntutbox_analytics_consent`（`Domain=.ntutbox.com`），與官網共用；
  同意前不載入 gtag.js、不建 GA cookie；撤回入口在官網隱私頁。
- 事件契約與參數 enum 的唯一真相來源：`apps/web/src/lib/analytics/events.ts`。

## 維運備忘
日常操作（補爬、重新發佈、選課季、告警處理、門檻變數）見 `infra/README.md`「維運 runbook」。
- **學期滾動**：`ACTIVE_TERMS` 留空即自動跟進 `current-term`（學校上架新學期下拉會翻）；要同時追多個學期（如選課季）才設值。
- **歷史重爬**：Actions → maintenance → `task=backfill`、`dataset`＋`terms`（如 `110-1:115-1`）。
- **quality gate**：課數較線上 manifest 掉 >5%（`QUALITY_MIN_RATIO`）或 0 課 → 不發佈 R2（防殘缺資料發佈）。
