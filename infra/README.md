# infra — 部署 / CI

## 託管（決策 D6/D7）
- **爬蟲**：GitHub Actions（cron）。公開 repo 免費分鐘、長 job OK。**勿用 CF Workers 跑爬蟲**（50 子請求/CPU 上限）。
- **資料出口**：Cloudflare R2 → 自訂網域 `cdn.ntutbox.com/course/v1/…`（egress $0、邊緣快取）。Action 結束用 `wrangler` 推上去。
- **Web**：Cloudflare Pages，綁本 monorepo、**Root directory 設 `apps/web`**。網域 `course.ntutbox.com`。
- `api.ntutbox.com`：**預留**給未來動態後端（勿被靜態資料佔用）。

## 待辦
- `.github/workflows/crawl.yml`：cron 跑 `crawler/` → commit canonical NDJSON → `wrangler` 推 artifacts 到 R2。選課季可加密集的 enrollment-only 更新 job。
- R2 bucket + 自訂網域 + cache headers；`manifest.json`（含 sha256/dataset_version）。
- App 端省頻寬：按學期切檔、gzip/br、ETag 條件式請求、裝置快取。

> 不要把 `.env`、R2 金鑰、任何個資進 repo（公開）。憑證走 GitHub Secrets / Cloudflare 環境變數。
