# course-web OG 預覽圖（HTML 源稿 → 靜態 PNG）設計

- 日期：2026-07-06
- 對應 issue：#36（course-web 部分；App 那張 `og-share.png` 另做）
- 前置：#29（主頁 OG/metadata）、#30/#35（課名 OG 邊緣注入，已上線）

## 需求

全站（含分享連結）目前**沒有任何 `og:image`**，且 `twitter:card=summary_large_image` 宣稱有大圖 → 社群預覽卡只有文字、沒有圖。原本考慮的 AI 生成圖畫質不佳、後期改字困難。

→ 用 **HTML/CSS 當源稿**（可版控、可編輯、向量排版文字銳利），**截圖輸出靜態 PNG** 當 `og:image`。OG 圖必須是真的圖片檔——unfurl bot 不渲染 HTML，所以 HTML 只是源稿、PNG 才是產物。

## 目標

- 一張 **1200×630** 的全站共用 OG 圖（課名資訊靠 og:title 帶、圖上無動態內容）。
- 源稿進 repo；改文案＝改 HTML → 重截 → commit，一分鐘完成。
- 接進 Next metadata，全站與分享連結的預覽卡都有圖。

## 非目標（YAGNI）

- **不**做每課動態渲染 OG 圖（另一個大工程）。
- **不**做截圖自動化 build step（圖數月才改一次，手動重截即可）。
- **不**在本次做 App 的 `og-share.png` 替換（#36 剩餘部分；之後可沿用同一套「HTML 源稿→截圖」手法另做一輪）。

## 產物與流程

| 檔案 | 說明 |
|---|---|
| `apps/web/og/og-image.html` | 源稿：固定 1200×630 的單頁 HTML/CSS（自包含、無外部依賴；icon 以相對路徑或 data URI 引用） |
| `apps/web/og/README.md` | 重截步驟（headless Chrome 視窗 1200×630 → 截圖存 `public/og.png`） |
| `apps/web/public/og.png` | 產物：部署後 URL = `https://course.ntutbox.com/og.png` |

- 截圖用 headless Chrome（開發時以 chrome-devtools 直接截）；輸出解析度 1200×630（若檔案大小允許可 2x 縮回，以文字銳利為準）。
- `og/` 目錄不在 `public/` 內 → 源稿不會被部署出去。

## 畫面構圖（1200×630，亮色）

- **底**：網站同款淡藍紫漸層（glass 背景色組）。
- **左（品牌區）**：北科盒子 app icon（repo 內 `src/app/icon.png`，藍盒＋翻開的書）＋「北科盒子 排課」大字＋標語一句（初稿「查課・排週課表・衝堂學分即時檢查」，mockup 時定稿）。
- **右（視覺區）**：迷你週課表圖形——圓角格線＋數塊網站同款藍色漸層課塊＋一塊橘色衝堂塊當亮點；玻璃卡片感（微浮起/傾斜視 mockup 效果決定）。
- 色彩/圓角對齊 `apps/web/AGENTS.md` 設計規範（accent 藍、橘=衝堂、圓角級距）。

## 接線（metadata）

- `apps/web/src/app/layout.tsx`：metadata 補 `openGraph.images` 與 `twitter.images`（**絕對網址** `https://course.ntutbox.com/og.png`，含 width/height/alt）。
- `twitter:card` 維持 `summary_large_image`。
- **worker 不動**（#30 的邊緣注入只改 title/description，不碰 image）。

## 驗證

1. Mockup 截圖給使用者視覺定稿（可迭代數版）。
2. `npm run build` 後 `out/index.html` 含 `og:image`（絕對網址）；lint/tsc/tests 綠。
3. 部署後：`curl` 正式站 HTML 見 `og:image`；`curl -I /og.png` 200。
4. 使用者真機貼 LINE/iMessage 看完整預覽卡（課名標題＋圖）。

## 風險

- 預覽卡快取：LINE/FB 等對同一 URL 的卡片有快取，上線後舊連結可能短時間仍顯示無圖（新連結/加參數即可看到新卡）。
- PNG 檔案大小：漸層大圖 PNG 可能偏大；必要時輸出 1x 或改 JPEG/品質壓縮（以 <300KB 為目標）。
