# ntutbox-course · 北科盒子 排課系統

[![試用](https://img.shields.io/badge/試用-course.ntutbox.com-3b82f6)](https://course.ntutbox.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

公開、免登入的**台北科技大學排課規劃器**：在選課開放前查課、排課、即時檢查衝堂與學分，排好後（規劃中）匯出一份選課計畫導入「北科盒子」iOS App 完成送件。

> **定位**：Web 端只做**規劃**——不登入、不跨域打學校系統、不代送。正式送件由北科盒子 iOS App 負責；Web ↔ App 只透過「選課計畫」串接。

🔗 **立即試用 → [course.ntutbox.com](https://course.ntutbox.com)**

![排課器（桌面）](docs/screenshots/planner-desktop.png)

<p align="center"><img src="docs/screenshots/planner-mobile.png" alt="排課器（手機）" width="300"></p>

## 狀態

公開**初步驗證**中。資料涵蓋 110-1 起 **11 個學期、約 3.2 萬筆開課**，由 GitHub Actions 定期更新。

| | 範圍 |
|---|---|
| ✅ 已上線 | 課程爬蟲與資料管線（P0）、Web 排課器核心迴圈（P1 · M1） |
| 🚧 規劃中 | 選課身分 / 六類選課階段分類（M2）、匯出選課計畫 → App 匯入（M3 / P2）、App 半自動送件（P3） |

## 功能（目前）

- **免登入查課**：全文搜尋課名 / 教師 / 課號 / 課程編碼（前端 bigram，離線可用）
- **多維篩選**：學院 / 系所 / 班級（連動）、星期 / 節次、必選修、英語授課（EMI）
- **週課表**：週 / 日檢視，資料驅動欄位（週末有課才顯示）
- **衝堂偵測**：同格堆疊志願序，衝堂格醒目標示
- **學分統計**：以第一志願計、排除佔位課
- **課程詳情**：含教學大綱（課程大綱 / 進度 / 評量 / 教材…）
- **草稿**：localStorage 自動保存，逐學期獨立
- **無固定時段托盤**：沒有上課節次的課（如實務專題）獨立列出
- **PWA**：Service Worker 快取、Apple / Liquid-Glass 風格、支援深色與減動偏好

> 節次採北科實際制：`1,2,3,4,N(中午),5,6,7,8,9,A,B,C,D(晚上)`；衝堂僅以「星期 × 節次」交集判定。

## 架構

![系統架構](docs/diagrams/01-architecture.png)

```
GitHub Actions（Python 爬蟲, cron）
  └─ aps.ntut.edu.tw/course/tw/（公開課程查詢）
     → canonical NDJSON（git 版控；commit 歷史＝免費的選課人數時序）
     → v1 JSON artifacts → Cloudflare R2（cdn.ntutbox.com/course/v1/）
Web（Next.js PWA · 靜態匯出 + 前端搜尋 + Service Worker）
  └─ course.ntutbox.com ── 匯出選課計畫（規劃中）→ 北科盒子 iOS App
```

> 更多圖（每日管線、資料模型、抓取邏輯、兩種抓取節奏）見 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## Monorepo 結構

| 路徑 | 內容 | 技術 |
|---|---|---|
| `apps/web/` | 排課 Web / PWA | Next.js 16 · TS · Tailwind · shadcn（Apple / Liquid-Glass 主題） |
| `crawler/` | 課程目錄 / 大綱爬蟲 | Python · Pydantic v2 · uv |
| `packages/schema/` | 資料合約（Pydantic → TS 型別生成） | — |
| `infra/` | Cloudflare（R2 / Workers）· GitHub Actions | wrangler |
| `docs/` | 設計 / 決策 / 架構圖 | — |

> 資料合約以 `crawler/models.py`（Pydantic）為單一真相，產生 TS 型別給 Web、（未來）Codable 給 iOS。

## 本機開發

### Web（`apps/web/`）

```bash
cd apps/web
pnpm install
pnpm dev          # http://localhost:3000（開發用本地 fixtures：public/data/v1）
pnpm test         # vitest
pnpm typecheck
pnpm build        # 靜態匯出到 out/
```

正式資料來自 `NEXT_PUBLIC_DATA_BASE_URL`（預設 `https://cdn.ntutbox.com/course/v1`）；未設時走本地 `public/data/v1` fixtures。

**用手機在區網實機測試**：`next.config.ts` 已設 `allowedDevOrigins`（涵蓋常用私網段與 `*.local`）。手機接同一 WiFi，開 `http://<你的-mac>.local:3000`（或 `http://<LAN-IP>:3000`）即可；用 `.local` 主機名最穩，IP 變動也免改。

### 爬蟲（`crawler/`）

```bash
cd crawler
uv venv .venv && uv pip install -p .venv/bin/python -e '.[dev]'
.venv/bin/pytest
.venv/bin/python -m ntut_catalog crawl --terms 115-1 --out ../data --force
```

詳見 [`crawler/README.md`](crawler/README.md)。

## Roadmap

- **P0 — 資料 / 爬蟲**（✅）：穩定產出 catalog / classes / periods / 大綱 JSON
- **P1 — Web 排課器**（🚧 M1 已上線；M2 身分與階段分類、M3 匯出進行中）：搜尋 / 週課表 / 衝堂 / 學分 / 階段分類 / 草稿 / 匯出
- **P2 — 匯出 plan → App 匯入確認**（Universal Link / URL Scheme）
- **P3 — App 半自動送件**（依班級分組批次）+ 結果回寫
- **P4 — 進階**：替代課 / 畢業學分 / 評價 / 行事曆

## 貢獻

歡迎 issue / PR。動手前請先讀 [`CLAUDE.md`](CLAUDE.md) 與 [`docs/DESIGN.md`](docs/DESIGN.md)（資料模型、選課規則、後端實證）。慣例：

- 走 PR 進 `main`；多人 / 多代理並行時各開 git worktree + topic branch，勿共用 `main`。
- **不得提交任何個資**（學號、帳密、session、特定學生班級 / 可選課程、`.env`）。本 repo 為公開。

## 致謝

資料結構與前人經驗參考自 gnehs 開源「北科課程好朋友」（[ntut-course-crawler-node](https://github.com/gnehs/ntut-course-crawler-node) / [ntut-course-web](https://github.com/gnehs/ntut-course-web)，ISC）。本專案為**獨立重寫、非衍生 fork**。

## 免責

非台北科技大學官方系統，僅供選課規劃參考；正式選課結果以校方系統為準。

## License

[MIT](LICENSE) © 2026 PoterPan
