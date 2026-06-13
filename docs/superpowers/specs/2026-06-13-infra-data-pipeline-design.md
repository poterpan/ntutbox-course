# ntutbox-course 資料管線 infra — 設計 spec

> 狀態：設計定案（2026-06-13，使用者已批准；含 Codex 審查修正）。下一步＝writing-plans 產實作計畫。
> 依據：`docs/DECISIONS.md` D6/D7、`docs/DESIGN.md` §4.3/§4.5、`infra/README.md`。
> 審查：Codex 2026-06-13 審過（修正紀錄見文末）。

## 目標
把 P0 完成的爬蟲變成自動化管線：**GitHub Actions cron 爬 active term → commit canonical（catalog 結構 + classes + enrollment snapshot）→ 從 canonical 重建完整 v1 → wrangler 推 v1 到 Cloudflare R2 → 經 `cdn.ntutbox.com/course/v1/` 供 web/iOS fetch**。

## 為什麼 GitHub Actions 當大腦、不從 Cloudflare 綁
- R2 是被動物件儲存，**只能被 push**，無「CF 監看 git 自動拉資料」機制。
- CF builds（Pages/Workers Builds）是 **push 觸發的 build/deploy**、非 cron；CF cron 只能觸發 Worker，而 Worker 有 50 子請求 + CPU 上限跑不動爬蟲（D6 已否決）。
- 管線需 cron + 長 job + 回寫 git（enrollment snapshot）→ 全是 GitHub Actions 的主場。
- **CF git 整合留給 P1 web app 部署**（Pages/Workers 連 repo、Root directory=`apps/web`），非本 spec 範圍。

## 資料流
```
cron (GH Actions, 04:00 Asia/Taipei；觸發僅 schedule + workflow_dispatch，無 push trigger → 不會自迴圈)
  → checkout main(code) + checkout orphan `data` branch 到 data/canonical/
  → crawl active term --force (ntut_catalog；--force 是因為要刷新 enrollment，見下)
  → 更新 canonical: catalog.ndjson(結構) + classes.json + enrollment/{date}.ndjson(時序)
  → 對【data branch】commit+push（分兩判斷：catalog/classes 結構有變才 commit；enrollment snapshot 視需要 commit；bot 身分）
  → build-v1：從 canonical 重建【完整】v1（所有學期）→ 產 manifest
  → quality gate（課數驟降/0 課/失敗率高 → fail，不發佈）
  → publish：wrangler 推【變動的】v1 物件 → 全部成功驗證後，最後才推 manifest
GH Actions 持 scoped Cloudflare API token（R2 write）往 CF 推（單向）。
```

## Branch 模型（使用者決策：canonical 走 orphan data branch，比照 gnehs）
- **`main`**：只放 code（crawler / apps/web / packages/schema / infra / docs）。**完全不含 data**（`.gitignore` 擋整個 `data/`）→ code 貢獻者 `git clone` 保持輕、main 歷史只有 code 變更。
- **`data`（orphan branch，與 main 無共同歷史）**：root = canonical 樹（`{term}/catalog.ndjson`、`{term}/classes.json`、`{term}/enrollment/{date}.ndjson`）。每日 bot commit 推到這裡，**不洗 main**。git log 時序分析照樣可得（`git log data -- ...`）。
- **v1 不進任何 branch**：純 R2 發佈目標，CI 從 canonical 重建（ephemeral）。
- **遷移**：P0 已把 canonical commit 進 main（`4201f3f`）。因 repo 尚未 push 任何 remote，趁公開前：建 orphan `data` branch 收 canonical → 從 main 歷史用 `git filter-repo` 移除 `data/canonical`（保持 main 真正乾淨）→ main `.gitignore` 改擋整個 `data/`。

## 核心原則：canonical = 完整單一來源，v1 完全可由它重建
（Codex 修正：v1 gitignore → CI 缺歷史 v1 → manifest 掉歷史學期）
- **canonical（git `data` branch，完整真相）**，逐學期：
  - `canonical/{term}/catalog.ndjson` — 純結構課程（**不含** volatile enrollment、**不含**爬取時間戳）
  - `canonical/{term}/classes.json` — 班級目錄（小；v1 classes 與 join lookup 的來源）
  - `canonical/{term}/enrollment/{date}.ndjson` — enrollment 時序（append-only，每行 `{offering_id, enrolled_count, withdrawn_count, observed_at}`）
- **v1（R2，gitignore，由 canonical 重建）**：catalog.json（envelope）＋ classes.json ＋ periods.json（靜態，來自 code）＋ enrollment.json（latest = 最新 snapshot）＋ manifest.json。
- **CI 發佈前一律 `build-v1`（重建全部學期的 v1）再產 manifest** → manifest 永遠涵蓋全部學期，與 R2 物件一致。

---

## Phase A — Enrollment 分離 + canonical 集合（schema/crawler 前置）

**問題**：catalog 內嵌 `enrolled_count/withdrawn_count/observed_at` 與 envelope `generated_at`，每日爬讓 catalog 每天 diff/換 sha → 污染 git、白白讓 client 重抓。

**設計**（落實 §4.5「enrollment 與目錄分離」）：
- **catalog 純結構**：
  - canonical `catalog.ndjson`：每行 `CourseOffering`，embedded `enrollment` 清空（counts/observed_at = None；capacity 本即恆 None）。
  - v1 `catalog.json`：envelope 不放爬取時間戳（`generated_at`/`freshness.*_at` 設 None 或移除）→ 結構沒變則 **byte 穩定、sha 不變**。catalog 的 `dataset_version` ＝ 其結構內容 sha256（= manifest 裡 catalog.json 的 sha）。
  - ⚠️ **不可 mutate 共用 Enrollment 物件**（Codex：`EnrollmentLatest.counts` 與 `course.enrollment` 同物件）→ 輸出 structural catalog 時用 model_copy/序列化 exclude，不改 `result` 內的物件。
  - ⚠️ **structural catalog 輸出時移除 raw_fields 中的人數/撤選欄位**（malformed row 整列入 raw_fields 會夾帶 volatile 值 → 隱性每日 diff；目前 malformed=0，但要防）。
- **enrollment 數字活在兩處**：
  - canonical `enrollment/{date}.ndjson`（每日 append 小檔，**時序**；同日 rerun → 覆寫同日檔）。
  - v1 `enrollment.json`（latest overlay = 最新 snapshot 包成 `EnrollmentLatest`，R2 短快取）。
- **classes 進 canonical**：把 `classes.json` 納入 git（逐學期），作為 v1 classes 與 build-v1 join lookup 的來源。
- **既有 11 學期遷移**（離線、不重爬）：擴充 `rederive`/新增 `build-canonical`：把現有資料的 enrollment 從 catalog 抽出 → 種初始 `enrollment/{today}.ndjson`；catalog 去 volatile + 去時間戳；classes.json 落到 canonical。產出後移到 orphan `data` branch（見 Branch 模型）。
- **crawler skip/resume 修正**（使用者審查）：現行 `cli.py` 的 skip 檢查 `data/v1/{term}` 存在性；v1 已是衍生物 → 改檢查 **canonical**（`data/canonical/{term}/catalog.ndjson`）。skip/resume 只服務「歷史 backfill 跳過已完成學期」；**daily active-term 一律 `--force`**（要刷新 enrollment，不可被 skip）。

**元件**：
- `artifacts.py`：`write_term` 輸出 structural catalog（非 mutate）；新增 `write_enrollment_snapshot(result, out_dir, date)`；classes 同時寫 canonical。
- 新增 `build_v1(canonical_dir, out_dir)`（或擴充 artifacts）：讀全部 canonical 學期 → 重建完整 v1（catalog/classes/periods/enrollment）→ `write_manifest`。
- `cli.py`：skip 檢查改看 canonical；daily 走 `--force`。
- `rederive.py`：擴充為一次性遷移（strip volatile + 去時間戳 + 落 canonical classes + seed snapshot），冪等。

**驗收**：同日跑兩次 active-term 爬取，`catalog.ndjson`/`classes.json` 無 git diff；每跑產一個 enrollment snapshot；v1 catalog 不含數字/時間戳且 sha 穩定、enrollment.json 含數字；`build-v1` 由 canonical 重建出的 v1 與直接爬出的一致；11 學期遷移後全過 pydantic 驗證。

---

## Phase B — build-v1 + R2 發佈

**publish 元件**：`infra/publish.py`（workflow 與本機共用）。
- 流程：`build-v1`（完整重建）→ **quality gate** → 逐檔 `wrangler r2 object put <bucket>/course/v1/<relpath> --file <path> --content-type application/json --cache-control <ttl>` → 全部 term files 成功並 HEAD 驗證 size 後，**最後才推 manifest.json**（原子性：manifest 永遠指向已存在物件）。
- 參數：`--bucket`、`--terms`（只推指定學期 + manifest）、`--all`（初次全量）、`--dry-run`（無憑證可測，印上傳清單 + 將套的 headers）。
- R2 key 前綴 `course/v1/...` 對齊 `cdn.ntutbox.com/course/v1/...`（D7 path 分產品）。
- **不預壓縮**：存未壓縮 JSON，靠 CF 邊緣自動 gzip/brotli（manifest sha256 對未壓縮 JSON，與邊緣壓縮不衝突——Codex 確認）。R2 原生 ETag 供條件式請求。

**Quality gate**（Codex：別發佈殘缺資料）。發佈前對 active term 檢查，任一不過 → fail job、**不更新 R2/manifest**：
- 課數為 0；或較「上次成功」課數掉超過 **5%**（門檻可調，存於 repo variable）。
- 關鍵查詢失敗（Subj -2 空、>10% 系所查詢失敗）。
- 「上次成功課數」基準：git 中上一版 `canonical/{term}/catalog.ndjson` 行數（本地可靠、不依賴 remote）。

**Cache-Control**（每檔上傳時設）：
- `manifest.json`：`public, max-age=300`。
- `catalog/classes/periods.json`：`public, max-age=3600`（靠 manifest sha256 + ETag 304）。
- `enrollment.json`：`public, max-age=300`（選課季可降到 60–120，見 fast-follow）。

**CORS**（R2 bucket policy）：`AllowedOrigins`=`https://course.ntutbox.com`、`http://localhost:3000`（dev）；`AllowedMethods`=`GET,HEAD`；`ExposeHeaders`=`ETag`。**不放寬成 `*`**（未來 staging 網域另列）。

**驗收**：`publish.py --dry-run` 列出正確 key 對映 + headers；quality gate 對人造殘缺資料會 fail；實推後 `curl -I https://cdn.ntutbox.com/course/v1/manifest.json` 回 200 + 正確 `cache-control`、`content-encoding`、`access-control-allow-origin`；manifest 涵蓋全部學期。

---

## Phase C — GitHub Actions

**`.github/workflows/crawl.yml`**：
- 觸發：`schedule: cron '0 20 * * *'`（= 04:00 Asia/Taipei，台北無 DST）＋ `workflow_dispatch`（輸入 `terms`、`force`）。**無 `push` trigger** → 對 data branch 的 commit 不會自迴圈（故 `[skip ci]` 非必要）。
- `permissions: contents: write`；`concurrency: group: crawl-${{ inputs.terms || vars.ACTIVE_TERMS }}, cancel-in-progress: false`（Codex：防 schedule 與 dispatch 互撞）。
- 步驟：
  1. checkout `main`（code）到 root；checkout orphan `data` branch 到 `data/canonical/`（`actions/checkout` 第二步 `ref: data, path: data/canonical`）。
  2. setup Python 3.12 + 裝 `crawler`。
  3. **驗證 `terms` 輸入**（regex `^\d{3}-[123](:\d{3}-[123])?(,...)?$`，擋注入）→ 讀 `vars.ACTIVE_TERMS`（預設 `115-1`）。
  4. 記下基準：`wc -l` 現有 `data/canonical/{term}/catalog.ndjson`（quality gate 用）。
  5. `ntut_catalog crawl --terms $TERMS --force`（daily 一律 force 以刷新 enrollment；含寫 enrollment snapshot）。
  6. **資料紅線掃描**（擋學號樣式/cookie/session/token/完整 HTML 錯誤頁進 canonical，特別查 `raw_fields`）。
  7. 在 `data/canonical`（= data branch 工作樹）內 commit + push 到 `data` branch：catalog/classes 有結構 diff → commit（`data(catalog): ...`）；enrollment snapshot → commit（`data(enrollment): {term} {date}`）；皆無 → 不 commit。push 前 `git pull --rebase`（Codex：防 reject）。
  8. `infra/publish.py --terms $TERMS`（build-v1 全量 + quality gate + 原子發佈）。
- **只爬 active term**：歷史學期凍結，不每日重爬 → 對學校 ~5 分鐘輕負載。歷史全量重爬走 `workflow_dispatch` + `terms=110-1:115-1`（backfill 時 skip-existing 由 canonical 判斷；`force` 可覆寫）。
- Secrets：`CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`（GH secrets）；`ACTIVE_TERMS`、bucket 名、quality-gate 門檻走 repo variables。

**驗收**：`workflow_dispatch` 手動跑 active term 成功；commit 落在 `data` branch、main 無新 commit；無結構變更時只產 enrollment commit、不產 catalog commit；同日 rerun 不 push 衝突；R2 出現新物件且 manifest 完整。

---

## 資料契約：enrollment overlay merge（實作在 P1 web，契約在此定）
- web 拿 `catalog.json`（結構，enrollment 全 null）+ `enrollment.json`（overlay）。
- **以 `counts[offering_id]` 整體取代** catalog 課程的 `enrollment`（非逐欄 merge）；overlay 缺該課 → 視為 unknown/stale 並顯示警告。
- overlay 出現 catalog 沒有的 `offering_id`（選課季中途新課）→ 忽略（等下次 catalog 重抓）。
- catalog 有但 overlay 沒有（中途下架）→ 標 unknown/stale。
- client 一律**先比 manifest sha**：catalog 變更先重抓 catalog，再套 overlay。
- 提醒（§4.5/§4.6）：**搶課權威是 cwish live、非此靜態人數**；catalog 無容量上限（capacity 恆 null）→ 只顯示絕對人數 + 陳舊警告。

## 選課季 fast-follow（本 spec 不實作，留掛勾 + 觸發條件）
選課季 enrollment 快速跳動，但**規劃用途 15–60 分鐘新鮮度即足**（送件權威在 App 打 cwish live）。且學校此時負載最高，**不可高頻狂掃**（gnehs 經驗：太快會被封）。
- **何時做**：web（P1）上線後、下一個選課季（開學 oads 加退選 / 116 學年預選）前。本輪 115-1 預選（6/8–6/19）因 web 未上線、無消費者，不趕。
- **要加**：① 爬蟲 `--enrollment-only` 模式（只重打各系所 QueryCourse 讀人/撤兩欄 ~61 請求，跳過 Subj 與學制查詢、跳過 catalog/classes 重產，只更新 enrollment.json + snapshot）；② `crawl-enrollment.yml` 第二支 workflow，選課季每 30–60 分鐘跑（保守 + 既有退避），用 repo variable `ENROLLMENT_FAST_UNTIL=<date>` 過期自動 no-op；③ git snapshot 維持粗顆粒（每日/每小時一筆，避免 commit 洗版），R2 enrollment.json 高頻刷新；④ 選課季把 enrollment.json/manifest 的 max-age 降到 60–120s。

---

## 資源建立（用 `gh`/`wrangler` 執行，但**逐一徵得使用者確認**——對外/不可逆）
1. 分支重整（push 前）：建 orphan `data` branch 收 canonical、從 main 歷史 `git filter-repo` 移除 `data/canonical`、main `.gitignore` 改擋整個 `data/`。→ `gh repo create`（**public**，依 CLAUDE.md）+ 設 remote + push `main` 與 `data` 兩 branch。
2. `wrangler r2 bucket create ntutbox-cdn`（預設名；serves `cdn.ntutbox.com`、他產品走別 path）→ 綁 custom domain `cdn.ntutbox.com` → 套 CORS policy。
3. GH secrets/variables 設定（token、account id、ACTIVE_TERMS、bucket、quality-gate 門檻）。
4. `infra/SETUP.md`：記錄 token scopes（R2 Edit）、DNS、CORS、所有手動步驟，供日後/他人重現。

## 明確排除（YAGNI）
- enrollment-only 快速模式 / 選課季高頻 workflow → 上方 fast-follow，本 spec 不做。
- web fetch client / 服務、overlay merge 實作（P1）。
- `api.ntutbox.com`（預留）、二進位格式 / SQLite 發佈（延後給 iOS/進階版）。

## 建置順序
A（enrollment 分離 + canonical classes + skip-check 改 canonical + 遷移 + build-v1）→ B（publish.py + quality gate + 原子發佈，可 --dry-run 先驗）→ 分支重整 + 資源建立（確認後）→ C（workflow 雙 checkout + --force + 紅線掃描 + concurrency）→ 端到端：dispatch 跑一次 active term，驗 R2 + data branch commit。

## 使用者審查修正紀錄（2026-06-13）
- ✅ **daily 要 --force**（真問題）：skip 檢查改看 canonical；daily active-term 一律 --force 否則空轉、不刷新 enrollment。已納入 Phase A/C。
- ℹ️ **data/v1 進 gitignore**：**已是現況**（P0 commit 即加 `data/v1/`，`git ls-files data/v1`=0、check-ignore 確認）；本次再因 Branch 模型擴大為 main 擋整個 `data/`。
- ✅ **canonical 放 orphan `data` branch**（架構決策）：main 純 code、輕 clone；data branch 收 canonical + 每日時序；不洗 main 歷史。已納入 Branch 模型 + 資料流 + Phase C + 資源建立。

## Codex 審查修正紀錄（2026-06-13）
納入：catalog 去爬取時間戳（結構 sha 當版本）；不 mutate 共用 Enrollment；canonical 完整可重建 v1 + manifest 涵蓋全學期；quality gate；R2 原子發佈（manifest 最後推）；workflow concurrency + pull --rebase；commit 拆 catalog/enrollment；terms 輸入驗證；資料紅線掃描；structural catalog 去 raw_fields 人數欄。契約類（overlay merge、cache 邊界）寫入「資料契約」段、實作標 P1。Codex 確認無虞：manifest sha256 vs 邊緣壓縮不衝突、CORS 對 course.ntutbox.com 足夠、cron 換算正確、public repo 收公開課程資料（含教師公開欄位、僅彙總人數）符合隱私邊界、R2 free tier 足夠、每日 snapshot 即使無變動仍寫是有意義的時序。
