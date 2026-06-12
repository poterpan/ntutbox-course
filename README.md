# ntutbox-course · 北科盒子 排課系統

公開、免登入的台北科技大學**排課規劃器**。在選課開放前查課、排課、即時檢查衝堂 / 學分 / 選課階段，排好後匯出一份選課計畫導入「北科盒子」App 完成送件。

> Web 端只做**規劃**（不登入、不代送）；正式送件由北科盒子 iOS App 負責。

## 狀態
🚧 早期開發中（設計完成，進入資料/爬蟲 PoC）。

## 架構
```
GitHub Actions (Python 爬蟲, cron)
  └─ aps.ntut.edu.tw/course/tw/ (公開課程查詢)
     → canonical NDJSON (git, 留人數時序)
     → JSON artifacts → Cloudflare R2 (cdn.ntutbox.com/course/v1/)
Web (Next.js PWA, 靜態 + 前端搜尋 + Service Worker)
  └─ course.ntutbox.com  ── 匯出選課計畫 → 北科盒子 App
```

## 結構（monorepo）
| 路徑 | 內容 | 技術 |
|---|---|---|
| `apps/web/` | 排課 Web/PWA | Next.js · TS · Tailwind · shadcn（Apple/Liquid-Glass 主題） |
| `crawler/` | 課程目錄爬蟲 | Python · pydantic |
| `packages/schema/` | 資料合約（Pydantic→TS 型別） | — |
| `infra/` | Cloudflare / CI | wrangler · GH Actions |
| `docs/` | 設計與決策 | — |

開發前請讀 `CLAUDE.md` 與 `docs/DESIGN.md`。

## 致謝
資料來源結構與前人經驗參考自 gnehs 開源「北科課程好朋友」（[ntut-course-crawler-node](https://github.com/gnehs/ntut-course-crawler-node) / [ntut-course-web](https://github.com/gnehs/ntut-course-web)，ISC）。本專案為獨立重寫、非衍生 fork。

## 免責
非台北科技大學官方系統。正式選課結果以校方系統為準。

## License
TBD（公開前確認）。
