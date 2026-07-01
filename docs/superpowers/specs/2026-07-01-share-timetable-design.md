# 分享功能 — F-B：分享整份課表（web→web）設計

> 狀態：已核可，待實作。日期：2026-07-01。相關：Issue #28（F-B 段）。
> 承接 F-A（#29）。F-C（匯出 App）另立 spec，與本文共用 payload 概念。

## 背景與範圍
分享功能三子 feature 的第二個。收件者點連結 →（在自己的系統內）彈出「分享的課表」唯讀彈窗，可與自己的課表快速切換對比，並可一鍵匯入。**不污染接收者草稿**。

沿用 F-A 已建好的基礎：`useShareLink`（收件端進站解析）、`shareOrCopy`（觸控原生面板／桌面複製）、`components/ui/toast.tsx`。

### 目標
- 使用者一鍵分享目前排好的整份課表。
- 收件者在**自己的排課系統內**彈窗看到對方課表（唯讀），關掉後有懸浮鈕可再叫出 → 快速與自己的對比。
- 可「複製到我的規劃」（明確動作；有既有排課時可選合併／取代）。

### 非目標（YAGNI）
- 不開新分頁 / 新路由（改用根路徑 `?plan=` + 彈窗，利於對比、且與 F-A 同套路）。
- 不做「疊影同格對比」（分享課疊畫在自己格線上）—— 對比更強但渲染/衝突視覺複雜，列為未來加值。
- 不做逐堂挑選匯入（僅整份匯入）。
- 不做課名 OG 預覽（#30）；分享文字已能帶課表標題。
- shared plan 不跨 reload 保留（session-only，v1 限制）。

## 關鍵約束（專案現況）
- 無後端、純靜態、planning-only；連結自帶資料。
- 課表 = `termKey` + `placed[]`（`offering_id` + `priority`）；`offering_id` 逐學期跳動 → 連結必帶 term。
- `WeeklyGrid` 目前直接讀 `draft-store.placed` + `useTermCourses.byId`。
- 學期切換：`ui-store.selectedTerm`（F-A 已提升）+ `TermSwitcher` 的 `useTermBootstrap`。
- 已有 `reconcile()` 容錯。

## 設計

### 1. 連結格式
根路徑 query param（與 F-A 同套路、#30 的 OG worker 在 `/` 就能吃到，且 `plan` 與 `course` 區隔）：
```
{origin}/?term=<term_key>&plan=<offering_id.offering_id.…>
例：https://course.ntutbox.com/?term=115-1&plan=360744.360745.360763
```
- **志願序用順序隱含**（第 1 個 = 志願 1…）→ 只存 offering_id、連結更短。匯出時依 priority 排序後 join；匯入時 priority = index+1。
- 約 15 堂 ~140 字元，遠低於 URL 上限。
- `lib/share/plan-link.ts` 純函式 `buildPlanLink({termKey, offeringIds, origin})` / `parsePlanLink(search)`（比照 `course-link.ts`）。

### 2. 收件端
擴充 `useShareLink`（已掛 PlannerLayout）：
1. 進站解析 `?plan`（與現有 `?course` 並存，各自處理）。
2. 有 `plan` → 設 active 學期 = `term`（觸發載入）→ 存入 `ui-store.sharedPlan = { termKey, offeringIds }` 並開啟彈窗；清 URL 上的 `term`/`plan` 參數（避免重整重觸發）。
3. **不修改 draft-store。** 切學期讓接收者「自己該學期的課表」在彈窗後面，對比同學期。

**分享課表彈窗（新元件 `SharedTimetableModal`）**：
- 手機 = 底部 Sheet、桌機 = 置中 Dialog（重用現有 `sheet.tsx`/`dialog.tsx`）。
- 內容：唯讀週課表（見 §3）+ 課清單 + 學分小結 + 標頭「分享的課表」+「複製到我的規劃」鈕。點課開現有資訊窗（唯讀）。
- 資料來源：`ui-store.sharedPlan.offeringIds` + `useTermCourses.byId`（該學期 catalog），**非 draft-store**。

**懸浮鈕**：`sharedPlan != null && 彈窗關閉` 時，畫面顯示懸浮 pill「分享的課表」→ 點擊重開彈窗。手機置於底部小結列上方、拇指可及。

### 3. 唯讀渲染（WeeklyGrid 參數化）
- `WeeklyGrid` 加可選 props：`placed?: PlacedCourse[]`（不傳 → 讀 `draft-store`，現狀不變）、`readOnly?: boolean`（關閉點格開 SlotPopover 等互動）。
- `SharedTimetableModal` 傳入 `placed`（由 sharedPlan.offeringIds map 成 `{offering_id, priority}`）+ `readOnly`。
- 現有主課表呼叫不帶 props → 行為完全不變。

### 4. 匯入流程
「複製到我的規劃」：
- 若接收者該學期 `draft.placed` 非空 → 彈「合併／取代」選擇；空則直接匯入。
- **合併**：附加 sharedPlan 中尚未排入的 offering_id，priority 接在現有最大值後。
- **取代**：draft.placed = sharedPlan（priority 依順序）。
- 匯入前切到該學期（`setSelectedTerm` + 該學期 draft 持久化 key）；以 `validIds` `reconcile` 略過失效課號並用既有 `staleDropped` 提示。
- 完成 → 關彈窗 + `clearSharedPlan()`（收懸浮鈕）→ 使用者在編輯器看到結果。

### 5. 寄件端
- 底部小結列（`CreditSummary` 區）加「分享課表」鈕。
- `buildPlanLink({ termKey, offeringIds: placed 依 priority 排序, origin })` → `shareOrCopy(url, "我的課表", "我的課表｜北科盒子 排課")`（觸控原生面板／桌面複製 + toast）。
- `placed` 為空 → 鈕禁用（或提示「先排幾堂再分享」）。

### 6. 狀態（ui-store 新增）
- `sharedPlan: { termKey: string; offeringIds: string[] } | null`
- `sharedPlanOpen: boolean`
- `openSharedPlan(plan)` / `setSharedPlanOpen(v)` / `clearSharedPlan()`
- session-only、非 persist；reload 不保留（v1）。

### 7. 邊界
- 空 `plan` / 非法 / term 不在資料集 → toast、不開空窗。
- sharedPlan 全數失效（資料更新）→ 彈窗顯示「此課表的課程多已更新或不存在」。

## 元件 / 檔案
| 檔 | 動作 |
|---|---|
| `lib/share/plan-link.ts`（新，+ test） | `buildPlanLink` / `parsePlanLink` 純函式 |
| `lib/planner/use-share-link.ts`（改，+ test） | 加 `?plan` 分支 → `openSharedPlan` |
| `components/planner/SharedTimetableModal.tsx`（新） | 唯讀彈窗（sheet/dialog）+ 匯入鈕 + 合併/取代選擇 |
| `components/planner/SharedPlanFab.tsx`（新，或併入 layout） | 懸浮鈕，`sharedPlan && !open` 時顯示 |
| `components/planner/WeeklyGrid.tsx`（改） | 加 `placed?` / `readOnly?` props（預設不變） |
| `components/planner/CreditSummary.tsx`（改） | 加「分享課表」鈕 |
| `store/ui-store.ts`（改） | sharedPlan 狀態 + actions |
| `components/planner/PlannerLayout.tsx`（改） | 掛 `SharedTimetableModal` + `SharedPlanFab` |

## 測試
- `plan-link.test.ts`：build→parse round-trip、順序=志願序、缺參數/空 plan 回 null、term 含 `-` 正確。
- `use-share-link.test.ts`：`?plan` → `openSharedPlan(termKey, ids)`、切學期、清參數、不動 draft；`?course` 舊行為不回歸。
- 匯入：合併（去重、priority 接續）、取代（覆蓋）、reconcile 略過失效。
- WeeklyGrid：帶 `placed` prop 時渲染該 plan、不讀 draft。

## 驗收
- 排好課 → 底部「分享課表」→ 連結（桌面複製 / 手機原生面板帶文字）。
- 開連結 →（自己系統內）彈出對方課表唯讀彈窗；關掉 → 懸浮鈕；點鈕再開 → 與自己的課表切換對比（同學期）。
- 「複製到我的規劃」→ 空草稿直接匯入；有排課則選合併/取代；結果進編輯器、失效課號提示。
- 收件端 draft-store 在「未按匯入前」完全不變。

## 與 #30 相容
整表連結 = 根路徑 `?term=&plan=`（`plan` 與 `course` 不同名）→ #30 的邊緣 OG worker 在 `/` 即可分辨單堂/整表、用同一份 `names.json` 查名。
