# ntutbox-course 資料管線 infra — 設計 spec

> 狀態：設計定案（2026-06-13，使用者已批准）。下一步＝writing-plans 產實作計畫。
> 依據：`docs/DECISIONS.md` D6/D7、`docs/DESIGN.md` §4.3/§4.5、`infra/README.md`。

## 目標
把 P0 完成的爬蟲變成自動化管線：**GitHub Actions cron 爬 active term → commit canonical（含 enrollment snapshot）→ wrangler 推 v1 JSON 到 Cloudflare R2 → 經 `cdn.ntutbox.com/course/v1/` 供 web/iOS fetch**。

## 為什麼 GitHub Actions 當大腦、不從 Cloudflare 綁
- R2 是被動物件儲存，**只能被 push**，無「CF 監看 git 自動拉資料」機制。
- CF builds（Pages/Workers Builds，含「Root directory」）是 **push 觸發的 build/deploy**、非 cron；CF cron 只能觸發 Worker，而 Worker 有 50 子請求 + CPU 上限跑不動爬蟲（D6 已否決）。
- 管線需 cron + 長 job + 回寫 git（enrollment snapshot）→ 全是 GitHub Actions 的主場。
- **CF git 整合留給 P1 web app 部署**（Pages/Workers 連 repo、Root directory=`apps/web`），非本 spec 範圍。

## 信任與資料流
```
cron (GH Actions, 04:00 Asia/Taipei)
  → crawl active term (ntut_catalog)
  → write canonical: catalog.ndjson(結構) + enrollment/{date}.ndjson(時序)
  → git commit（僅當 canonical 有變；[skip ci]、bot 身分、contents: write）
  → publish.py：wrangler 推 v1/*（catalog/classes/periods/enrollment + manifest）到 R2
       key 前綴 course/v1/...  →  cdn.ntutbox.com/course/v1/...
GH Actions 持 scoped Cloudflare API token（R2 write）往 CF 推（單向）。
```

---

## Phase A — Enrollment 分離（schema/crawler 前置）

**問題**：今天 catalog NDJSON 內嵌 `enrolled_count/withdrawn_count/observed_at`，每日爬會讓每行 `observed_at` 變動 → 3MB/日 無意義 diff，污染 git 歷史、違背「diff 有意義」目標。

**設計**（落實 §4.5「enrollment 與目錄分離」）：
- **canonical catalog NDJSON + v1 catalog.json = 純結構**：寫出時 embedded `enrollment` 清空（`enrolled_count/withdrawn_count/observed_at` 皆 None；`capacity` 本即恆 None）。→ 結構沒變則 git 零 diff。
- **enrollment 數字活在兩處**：
  - `v1/terms/{term}/enrollment.json`（latest overlay，R2 短快取，web 疊在 cached catalog 上）——**保留現有產物**，數字與 observed_at 在此。
  - canonical `canonical/{term}/enrollment/{date}.ndjson`（每日 append 的小檔，每行 `{offering_id, enrolled_count, withdrawn_count, observed_at}`）——**這就是時序**，per-day 一檔、append-only。
- **既有 11 學期遷移**（離線、不重爬）：擴充 `rederive`：從現有資料把 volatile enrollment 從 catalog（canonical+v1）清空，並種一份初始 `enrollment/{today}.ndjson`。

**元件**：
- `artifacts.py`：
  - `write_term` 寫 catalog 時，embedded enrollment 清空（純結構）。
  - 新增 `write_enrollment_snapshot(result, out_dir, date)` → `canonical/{term}/enrollment/{date}.ndjson`。
  - `enrollment.json`（v1 latest overlay）維持帶數字。
- `rederive.py`：擴充既有離線遷移（strip volatile + seed snapshot），冪等。
- 結構變動偵測**不需程式**：catalog 變純結構後，git 本身 diff 即可判斷要不要 commit catalog。

**驗收**：跑兩次 active-term 爬取（同日），catalog.ndjson 無 git diff；enrollment snapshot 每跑產一檔；v1 catalog 不含數字、enrollment.json 含數字；11 學期遷移後全過 pydantic 驗證。

---

## Phase B — R2 發佈

**元件**：`infra/publish.py`（被 workflow 與本機共用）。
- 逐檔 `wrangler r2 object put <bucket>/course/v1/<relpath> --file <path> --content-type application/json --cache-control <ttl>`（符合 infra/README「用 wrangler 推」決策）。
- R2 object key 前綴 `course/v1/...` 對齊 `cdn.ntutbox.com/course/v1/...`（path 分產品，D7）。
- 參數：`--bucket`、`--terms`（只推指定學期 + manifest；daily cron 推 active term）、`--all`（初次全量）、`--dry-run`（本機無憑證可測，印出將上傳清單）。
- **不預壓縮**：存未壓縮 JSON，靠 Cloudflare 邊緣自動 gzip/brotli（最簡；manifest sha256 對得上原始 JSON）。R2 原生 ETag 供條件式請求。R2 免費 10GB，36MB 不壓無虞。

**Cache-Control**（每檔上傳時設）：
- `manifest.json`：`public, max-age=300`（client 輪詢偵測變更）。
- `catalog/classes/periods.json`：`public, max-age=3600`（靠 manifest sha256 決定重抓；ETag 304）。
- `enrollment.json`：`public, max-age=300`（選課季常更新）。

**CORS**（R2 bucket policy，否則 web 跨域 fetch 失敗）：
- `AllowedOrigins`: `https://course.ntutbox.com`、`http://localhost:3000`（dev）。
- `AllowedMethods`: `GET, HEAD`；`AllowedHeaders`: `*`；`ExposeHeaders`: `ETag`。

**驗收**：`publish.py --dry-run` 列出正確 key 對映；實推後 `curl -I https://cdn.ntutbox.com/course/v1/manifest.json` 回 200 + 正確 `cache-control`、`content-encoding: br/gzip`（邊緣）、`access-control-allow-origin`。

---

## Phase C — GitHub Actions

**`.github/workflows/crawl.yml`**：
- 觸發：`schedule: cron '0 20 * * *'`（20:00 UTC = 04:00 Asia/Taipei，學校離峰）＋ `workflow_dispatch`（輸入 `terms`、`force`）。
- `permissions: contents: write`。
- 步驟：checkout → setup Python 3.12 + 安裝 `crawler`（uv/pip）→ 讀 repo variable `ACTIVE_TERMS`（預設 `115-1`，dispatch 可覆蓋）→ `ntut_catalog crawl --terms $ACTIVE_TERMS`（含寫 enrollment snapshot）→ `git add data/canonical && git commit`（僅當有變、訊息含 `[skip ci]`、`github-actions[bot]` 身分）→ `git push` → `infra/publish.py --terms $ACTIVE_TERMS`（推 active term + manifest 到 R2）。
- **只爬 active term**：歷史學期（110–113…）凍結，不每日重爬 → 對學校 ~5 分鐘輕負載、Actions 也快。歷史全量重爬走 `workflow_dispatch` + `force`。
- Secrets：`CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`（GH secrets）；`ACTIVE_TERMS`、bucket 名走 repo variables。

**驗收**：`workflow_dispatch` 手動跑 active term 成功；無結構變更時不產 catalog commit、但有 enrollment snapshot commit；R2 出現新物件。

---

## 資源建立（用 `gh`/`wrangler` 執行，但**逐一徵得使用者確認**——對外/不可逆）
1. `gh repo create`（**public**，依 CLAUDE.md「本 repo 將 public」）+ 設 remote + push（含 P0 已 commit 的歷史）。
2. `wrangler r2 bucket create ntutbox-cdn`（預設名；serves `cdn.ntutbox.com`、未來他產品走別的 path prefix）→ 綁 custom domain `cdn.ntutbox.com`（dashboard 或 API）→ 套 CORS policy。
3. GH secrets/variables 設定（token、account id、ACTIVE_TERMS、bucket）。
4. `infra/SETUP.md`：記錄 token scopes（R2 Edit）、DNS、CORS、所有手動步驟，供日後/他人重現。

## 明確排除（YAGNI）
- enrollment-only 快速爬蟲模式（active term 全爬 ~5min 已足；選課季再評估）。
- web fetch client / 服務（P1）。
- `api.ntutbox.com`（預留，不在本 spec）。
- 二進位格式 / SQLite 發佈（延後給 iOS/進階版）。

## 建置順序
A（enrollment 分離 + 遷移）→ B（publish.py，可 --dry-run 先驗）→ 資源建立（確認後）→ C（workflow）→ 端到端：dispatch 跑一次 active term，驗 R2 + git。
