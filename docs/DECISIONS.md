# 技術決策紀錄（ADR 摘要）

決策脈絡與細節以 `DESIGN.md` 為主；本檔聚焦「選了什麼、為什麼、考慮過的替代」。

## D1 — 獨立 repo（脫離 NTUT_Tools）
NTUT_Tools 是校務系統逆向 **PoC**（Python，throwaway 多）；排課是**產品**（多技術棧、要部署、對外）。混在一起會互相污染。→ 本 repo 為產品；NTUT_Tools 留作 PoC/研究參考（cwish/oads 送件邏輯在那驗證）。

## D2 — Monorepo（非多 repo / 非 submodule）
首要訴求「**AI Agent 好維護**」→ 單一 context 最易維護、schema 跨層改動原子化。資料集要當公共財可靠發佈 R2 + git canonical 達成，不需拆 repo。Cloudflare 綁定用 Pages「Root directory」分流即可，**submodule 是反模式**。

## D3 — 資料來源：舊版 `/course/tw/`（非 `/course/mobile/`）
實測：新版手機 UI 是換皮、POST 同一支 `QueryCourse.jsp`，但回傳只 11 欄、**拿掉所有 `code=` 連結**，官方標「僅供參考」。舊版 24 欄、含班級/教師/教室 code、課綱、人數——爬取所需結構全在舊版。

## D4 — 不沿用 gnehs JSON 格式，設計 typed v1（`crawler/models.py`）
gnehs 弱型別、`link` 綁死 JSP 路徑、中文檔名、缺 metadata、漏抓 EMI。→ 自有 Pydantic schema：型別化、丟 link 留 code、修別符號語意化、envelope/manifest、`offering_id`(課號) vs `course_code`(課程編碼) 分離、enrollment 拆 volatile + snapshots。gnehs 僅作開發期相容/參考。

## D5 — Web v1：靜態 JSON + 前端搜尋索引（非後端、非 SQLite-WASM）
情境＝不登入、不即時、公開近靜態資料、~5000 課。
- 排除 **Worker+D1**（後端對此情境不划算，留後路）。
- 排除 **SQLite-WASM**（對 5000 筆過重、Safari OPFS 雷、trigram 搜不到 1–2 字中文）。
- 選 **靜態 JSON + 前端 bigram 索引（FlexSearch/Orama）+ Service Worker**：零後端、離線 PWA、中文 bigram 比 SQLite trigram 好。
- canonical＝NDJSON（git）；iOS/進階版日後由同一 canonical 產 SQLite（GRDB+FTS5）。

## D6 — 託管：GitHub Actions（爬蟲）+ Cloudflare（出口）
GH Actions 公開 repo 免費分鐘、長 job、cron；資料 commit 進 git＝免費 enrollment 時序。**勿用 CF Workers 跑爬蟲**（50 子請求/CPU 上限）。對外走 Cloudflare R2（egress $0、邊緣快取、自訂網域），避開 GH Pages 100GB 軟上限與 ToS。

## D7 — 子網域（ntutbox.com）
- `course.ntutbox.com` → Web app
- `cdn.ntutbox.com/course/v1/…` → 靜態 catalog（**path 分產品**，未來別功能走 `/xxx/` 不撞名）
- `api.ntutbox.com` → **預留**動態後端（與靜態資料分流，不衝突）

## D8 — Web 前端：Next.js(React) + Tailwind + shadcn 骨架 + 自訂 Apple/Liquid-Glass 主題
- AI 好維護：React/Next 語料最大、agent 最流暢（Svelte 5 runes 太新、Nuxt 居中）。
- UIUX：shadcn 是無樣式 Radix 元件（你擁有），**換主題即不撞臉**；自訂 Apple 皮（系統字體棧、`backdrop-filter` 做 Liquid Glass、framer-motion；尊重 `prefers-reduced-transparency`/`motion`）。
- 多平台：RWD + PWA；iOS 獨立 Swift，只共用資料合約。
- 未採 Konsta UI（iOS 風元件庫）——以 shadcn＋自訂主題為主，AI 維護性與彈性較佳。

## D9 — handoff：選課計畫 payload（只帶課號+優先序+階段分組）
Web 排好 → Universal Link / URL Scheme 導入 App，App 確認後送件。payload 帶 `version/semester/dataset_version/studentContext(班級碼)/plans[phase 分組]/warnings`，**不帶課程內容**（App 用自身 catalog 還原）、**不含帳密**。模型見 `crawler/models.py` 的 `PlanPayload`。

## D10 — 送件鐵則（cwish live 實證）
後端嚴格驗 `(cunum, subj)`、cunum 綁本人授權範圍。→ 扁平清單必依課程所屬班級分組、各帶正確 cunum（本班碼/授權外班碼），不能全塞同一 cunum；cunum 來自 cwish live 清單。細節與錯誤對照表見 `DESIGN.md` §4.6。
