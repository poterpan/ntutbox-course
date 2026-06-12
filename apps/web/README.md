# apps/web — 排課 Web / PWA

Next.js + TypeScript + Tailwind + shadcn（自訂 Apple / Liquid-Glass 主題）。**無後端**：fetch 靜態 catalog JSON（`cdn.ntutbox.com/course/v1/`）→ 前端 bigram 搜尋索引 → Service Worker 快取（離線、可安裝）。

## 範圍（P1，不登入、不代送）
課程搜尋/篩選、視覺化週課表、衝堂檢查（day×period 交集）、學分統計、**選課階段分類**（preselection/preference_ballot/add_drop/program_registration/planning_only/unknown）、限制原因顯示、草稿（localStorage）、匯出選課計畫 payload。

## 重點
- 身分：使用者選「系所/年級/班」（從 `classes.json`，存 localStorage），用於本班/外班**規劃提示**；App 送件時以 live 為準覆蓋。**用班級碼比對、非名稱**。
- 節次：`1,2,3,4,N,5,6,7,8,9,A,B,C,D`（牆鐘時間取自 `periods.json`）。
- pool 班級（博雅/體育/英文）不可 naive 分類 → 依 `classes.json` 的 `kind` 處理。
- UI：shadcn 骨架 + 自訂 glass 主題（系統字體棧、`backdrop-filter`、framer-motion）；尊重 `prefers-reduced-transparency`/`prefers-reduced-motion`，低階裝置給不透明 fallback。
- 資料合約型別來自 `packages/schema`（由 crawler 的 Pydantic 生成）。

設計與規則：見 `../../docs/DESIGN.md`（§4.5 發佈格式、§4.6 分類/handoff/實證）。Cloudflare Pages 綁定時設 Root directory 指向本資料夾。
