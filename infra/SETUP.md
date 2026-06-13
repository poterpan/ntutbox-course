# infra — 上線設定（go-live runbook）

> 程式碼/設定已就緒（見 `crawl.yml`、`publish.py`、`redline_scan.py`、`r2-cors.json`）。
> 本檔是**對外資源建立**步驟——需在 Cloudflare/GitHub 實際開通。每一步做完再做下一步。
> 設計依據：`docs/superpowers/specs/2026-06-13-infra-data-pipeline-design.md`。

## 前置
- `gh` 已登入（`gh auth status`）、`wrangler` 已登入（`wrangler whoami`）。
- 網域 `ntutbox.com` 已在 Cloudflare（DNS 可加 `cdn` 子網域）。
- 本地已完成遷移：`data` branch 有 11 學期 canonical、`main` 為純 code。

## 1. GitHub repo（public）
```bash
# 在 repo 根目錄
gh repo create ntutbox-course --public --source=. --remote=origin --description "北科盒子 排課系統"
git push -u origin main
git push origin data          # 推 orphan data branch（canonical 時序）
```
> ⚠️ 公開前確認：`git ls-files | grep -i -E 'env|secret|key'` 應為空；`infra/redline_scan.py`（CI 已含）對 `data` branch 乾淨。

## 2. Cloudflare R2 bucket + 自訂網域 + CORS
```bash
wrangler r2 bucket create ntutbox-cdn
# 綁自訂網域（dashboard：R2 → ntutbox-cdn → Settings → Custom Domains → 加 cdn.ntutbox.com）
#   或 API：見 https://developers.cloudflare.com/r2/buckets/public-buckets/#custom-domains
# 套 CORS（允許 course.ntutbox.com 與本機 dev）
wrangler r2 bucket cors put ntutbox-cdn --rules "$(cat infra/r2-cors.json)"
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
gh variable set R2_BUCKET --body ntutbox-cdn
gh variable set ACTIVE_TERMS --body ""      # 留空＝workflow 自動偵測當前學期
gh variable set QUALITY_MIN_RATIO --body 0.95
```

## 5. 首次全量發佈（一次性）
```bash
# 本機（已登入 wrangler）把 11 學期 v1 推上 R2
python infra/publish.py --bucket ntutbox-cdn --all --out data --generated-at "$(date -u +%FT%TZ)"
```

## 6. 驗證
```bash
curl -I https://cdn.ntutbox.com/course/v1/manifest.json     # 200 + cache-control: max-age=300
curl -I https://cdn.ntutbox.com/course/v1/terms/115-1/catalog.json   # 200 + max-age=3600 + content-encoding
curl -s -H "Origin: https://course.ntutbox.com" -I https://cdn.ntutbox.com/course/v1/manifest.json | grep -i access-control
```

## 7. 啟用排程
- `crawl.yml` 已含 `schedule`（每日 04:00 台北）。可先手動跑驗證：
  - GitHub → Actions → "crawl catalog" → Run workflow（`terms` 留空＝自動當前學期）。
  - 確認：`data` branch 出現 `data(enrollment): ...` commit；R2 manifest 更新；無 catalog 結構 commit（結構未變時）。

## 維運備忘
- **學期滾動**：`ACTIVE_TERMS` 留空即自動跟進（學校上架新學期下拉會翻）；要釘住特定學期才設值。
- **歷史重爬**：Actions → Run workflow，`terms` 填 `110-1:115-1`。
- **quality gate**：課數較上次掉 >5%（或 0 課）→ job fail、不更新 R2（防殘缺資料發佈）。
- **選課季高頻 enrollment**：見 spec「選課季 fast-follow」（本期未實作）。
