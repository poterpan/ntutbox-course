# 分享連結課名 OG（邊緣注入）設計

- 日期：2026-07-02
- 對應 issue：#30
- 前置：#29（F-A 單堂分享 + 主頁 OG）、#31（F-B 整份分享）、#34（點課看詳情）

## 需求

Web 的分享連結（`course.ntutbox.com/?term=&course=`＝F-A 單堂、`?term=&plan=id.id…`＝F-B 整份）貼到 LINE / iMessage / Discord 時，unfurl bot 抓到的是**靜態 SPA 的 index.html**，OG 是通用文案（#29 設的「北科盒子 · 排課」），**看不到課名**。要在邊緣把 OG 標題/描述換成**實際課名**（頁面照常運作、真實使用者不受影響）。

純靜態 SPA 做不到（OG 要在 HTML 回應時就在）→ 需要邊緣 Worker + HTMLRewriter。

## 目標

- `?course=` → OG 顯示該課**中文課名**。
- `?plan=` → OG 顯示通用「分享的課表 · N 門課」。
- 其他請求（無分享參數、一般資源）→ 原樣通過，OG 維持 #29 的站台通用值。

## 非目標（YAGNI）

- **不**做每課渲染的 OG 圖片卡（沿用現有站台 OG 圖，只改標題/描述文字）。
- **不**做 UA 偵測（不分 bot/真人，只要帶分享參數就注入——對真人無害，SPA 照跑）。
- **不**動爬蟲抓取邏輯（只在既有 artifact 產生處多導出一個索引檔）。

## 資料來源（選定：names 索引檔）

Production 預設**不發**逐課 `course/{id}.json`（`publish.py --include-details` 預設 False）。課名一定拿得到的是 `catalog.json`，但它 2.4MB、邊緣 parse 太重。

→ **新增小索引檔** `terms/{term}/names.json` = `{ "<offering_id>": "<中文課名>" }`（~70KB、gzip ~20KB）。在**既有 artifact 產生處**從 catalog 導出，隨既有 cron 發佈流程自動產生 + 上傳 → **新學期零介入自動生效**。

## 架構

### 1) 資料：產出並發佈 `names.json`

- **`crawler/ntut_catalog/artifacts.py` `build_v1()`**：在寫 `catalog.json`（現行 L112）之後，用同一批 `courses` 導出：
  ```python
  names = {c.offering_id: c.name.zh for c in courses if c.name and c.name.zh}
  (v1 / "names.json").write_text(json.dumps(names, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
  ```
  （`CourseOffering.name` 為 `LocalizedText`，`.zh` 已確認。）
- **`infra/publish.py`**：把 `names.json` 加進每學期預設上傳清單（現行 `["catalog.json","classes.json","periods.json","enrollment.json","mprograms.json"]`）→ 每次 publish 自動上傳。
- **manifest**：**不**納入 `names.json`（避免動 `models.py` 的 `ManifestTerm`；OG worker 直接以 URL 取用，不靠 manifest）。
- **fixtures**：從既有 `apps/web/public/data/v1/terms/*/catalog.json` 導出對應 `names.json` 一併 commit（本地 dev + worker 測試要用）。

### 2) 邊緣：web 由 assets-only 改成 Worker + ASSETS binding

- **`apps/web/wrangler.jsonc`**：加 `main`（worker 進入點）、`assets.binding = "ASSETS"`（保留 `directory: ./out`、`not_found_handling: single-page-application`）、`vars.DATA_BASE_URL = "https://cdn.ntutbox.com/course/v1"`。
- **新增 `apps/web/worker/index.ts`**（wrangler 以 esbuild 內建打包，無需額外 build）：
  - `fetch(request, env)`：
    - 解析 URL。若 **`pathname === "/"` 且帶 `course` 或 `plan` 參數** → 進 OG 注入路徑；否則 `return env.ASSETS.fetch(request)`（原樣通過，含所有靜態資源與 SPA fallback）。
    - OG 路徑：`const res = await env.ASSETS.fetch(<index request>)` 取得 SPA HTML；解析 `term` + 課名 → `HTMLRewriter` 改寫 `<meta property="og:title">`、`og:description`、`twitter:title`、`twitter:description` 的 `content`；`og:image` 不動。回傳改寫後 HTML。
  - **課名解析**：
    - `?course=<id>`：抓 `${DATA_BASE_URL}/terms/${term}/names.json` → `names[id]`。og:title＝`{課名}｜北科盒子 排課`；og:description＝`在北科盒子 排課查看課程詳情、加入你的課表`。
    - `?plan=<id.id…>`：`n = ids.length`；og:title＝`分享的課表 · {n} 門課｜北科盒子 排課`；og:description＝`查看這份 {n} 門課的課表規劃`。不需課名 → **可不抓 names.json**。
  - **快取**：`names.json` 以 Cache API 或 `fetch(url, { cf: { cacheTtl } })` 邊緣快取；另在 module scope 存 `Map<termKey, Record<id,name>>` 供同 isolate 重用。TTL 足夠（課名少變），新學期靠不同 term key 自然取新檔。
  - **fallback（不可壞頁）**：term/參數缺、`names.json` 404、課號不在表、fetch/parse 失敗 → **不改 OG、原樣回 SPA**（維持 #29 通用值）。真人與 bot 都永遠拿得到可用頁面。

## 行為細節

- 注入只在 `pathname === "/"` 且有 `course`/`plan` 時發生；其餘 100% 走 `env.ASSETS.fetch`（零行為改變）。
- 真實使用者拿到的是「OG 已正確 + SPA 照常 hydrate」的 HTML（SPA 仍用 `useShareLink` 讀參數開窗，不受影響）。
- HTMLRewriter 只換既有 meta 的 `content`，不新增/刪除節點，結構最小變動。

## 邊界 / 失敗

| 情況 | 行為 |
|---|---|
| 無分享參數 / 靜態資源 | `env.ASSETS.fetch` 原樣 |
| `names.json` 尚未發佈（cdn 還沒有） | fallback 通用 OG（頁面正常） |
| 課號不在 names | fallback 通用 OG |
| 抓 names 逾時/錯誤 | try/catch → fallback，不阻塞回應 |
| `?plan=` | 只算數量、通用文案，不抓 names |

## 上線順序（重要）

Worker 要能顯示課名，**cdn 上得先有 `names.json`**。因此：

1. **先** 落地資料端（artifacts.py + publish.py + fixtures）並**跑一次 publish**（或等 cron）→ `names.json` 上 cdn。
2. **再** 落地/部署 web worker。

可拆兩個 PR（資料 → web），或同分支但驗收分兩段。Worker 的注入邏輯可**先用本地 fixtures 驗**（不依賴 cdn）。

## 驗證

- **資料端**：`crawler` 既有 pytest 綠 + 新增 `names.json` 產出的單元測試（給定 catalog → 導出 `{id:name}`）；`publish.py` 上傳清單含 `names.json`。
- **Worker 邏輯（本地）**：`wrangler dev` + `curl` 帶 `?course=`/`?plan=`，看回應 HTML 的 `og:title`/`og:description` 是否被改寫（`DATA_BASE_URL` 指向本地 fixtures 伺服器或含 names.json 的來源）；無參數 curl 確認原樣。
- **真機 unfurl**：`names.json` 發佈後，於 preview / prod 貼分享連結到 LINE / iMessage 看預覽卡出現課名。**這步需真機、無法只靠截圖**（使用者執行）。
- lint / tsc / build（web）全綠；轉成 worker 後一般資源與 SPA fallback 仍正常。

## 風險

- **assets-only → Worker 轉換**：確保非分享請求 100% 走 `env.ASSETS.fetch`（含 SPA fallback），不改變現有服務行為。轉換後先驗一般頁面/資源無異常。
- **邊緣 fetch 失敗不可炸頁**：所有課名解析包 try/catch、預設 fallback。
- **CI/Workers Builds**：Dashboard 既有「build && wrangler deploy」流程要能打包新的 `main` worker（wrangler esbuild 內建，預期 OK）；部署後確認 preview 正常。
