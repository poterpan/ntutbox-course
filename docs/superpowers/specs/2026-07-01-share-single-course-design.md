# 分享功能 — F-A：分享單堂課程（web→web）設計

> 狀態：已核可，待實作。日期：2026-07-01。相關：Issue #28。
> 這是「分享功能」三個子 feature 的第一個；F-B（分享整份課表）、F-C（匯出到 App）另立 spec。

## 背景與範圍

課程系統要能把課分享出去。整體拆成三個獨立 feature：

- **F-A（本文）**：分享**單堂課**（web→web）。收件者點連結 → 直接開該課的**現有資訊窗**（`CourseDetailDrawer`）。
- **F-B**：分享**整份課表**（web→web）。獨立唯讀檢視頁，**不併入**接收者草稿。共用 payload 設計。
- **F-C**：**匯出到 App**（web→app）。Universal Link 帶加選必要資訊；App 只做加選。與 F-B 共用 payload 合約。

F-A 是最小、最快、可立即驗證的一片，先做。

### 目標
- 使用者在課程資訊窗按「分享」→ 取得一個連結。
- 他人開連結 → 自動開啟該課的資訊窗，看到完整課程資訊。
- 收件端**不污染**其現有草稿（只是開窗；要不要排入由他自行操作）。

### 非目標（YAGNI）
- 不做整份課表分享（F-B）、不做 App 匯出（F-C）。
- 不做每堂課的社群預覽卡（rich OG）——無後端，屬未來。
- 不做短碼／後端；連結自帶資料。

## 關鍵約束（來自專案現況）
- Web 端**無後端、純靜態匯出（`output: export`）、planning-only、不送件**。
- 課程主鍵 `(term_key, offering_id)`；`offering_id` 逐學期跳動 → **連結必帶 term**。
- 草稿（`draft-store`）依學期分區存於 localStorage；已有 `reconcile()` 容錯基礎。
- 開資訊窗 = `useUiStore.openDetail(offeringId)`（`detailOfferingId` 狀態）。
- 學期切換走 `term-store` + `useTermBootstrap`；`TermSwitcher` 目前用本地 `selected` state 驅動 bootstrap。
- **專案目前無 toast 元件** → 本 feature 需新增一個極簡 toast。

## 設計

### 1. 連結格式
採 **query param**（純靜態無伺服器、前端讀取即可、零路由/SSG 成本）：

```
{origin}/?term=<term_key>&course=<offering_id>
例：https://course.ntutbox.com/?term=115-1&course=360744
```

- 用兩個明確參數，**不**把 term 與 offering_id 併成一段（避免 term_key 內的 `-` 造成解析歧義）。
- 不採路徑 `/c/<term>/<offering>`（靜態匯出須為 3 萬+課 `generateStaticParams`，不可行）或 hash（query param 更標準）。

### 2. 寄件端（產生連結）
- 在 `CourseDetailDrawer` 標題列加一顆「分享」圖示鈕（放標題列，不佔用底部主要動作區）。
- 點擊：
  1. 以目前檢視的 `term_key` + 該課 `offering_id` 組出連結。
  2. **觸控裝置**（`(hover: none) and (pointer: coarse)`）→ 叫出原生分享面板（title = 課名、url = 連結）。
  3. **桌面一律複製**（含有 `navigator.share` 的 Mac Chrome/Safari 也走複製，保持一致）→ `navigator.clipboard.writeText(url)` + toast「已複製連結」。
  4. clipboard 也失敗 → toast「複製失敗，請手動複製網址」。

> toast 以 portal 掛到 `document.body`、`z-[100]`，確保浮在資訊窗（Dialog backdrop z-50）之上、不被模糊遮擋。

### 3. 收件端（開啟連結）
新增 `useShareLink` hook，掛在 planner 根（`PlannerLayout`），進站執行**一次**：
1. 讀 `?term` 與 `?course`；兩者皆缺 → 不動作（正常進站）。
2. 設定 active 學期 = `term`（透過 term 切換機制）→ 觸發該學期資料載入。
3. 該學期資料就緒後，若 `offering_id` 存在 → `openDetail(offering_id)` 開資訊窗；不存在 → 見「錯誤處理」。
4. **不修改** `draft-store`（favorites/placed 不動）。切學期只改「檢視中的學期」，接收者各學期已存草稿不受影響。
5. 開窗後清掉 URL 上的 share 參數（`history.replaceState`），避免重整/分享時殘留、也避免二次觸發。

### 4. 錯誤處理（不靜默失敗）
- `offering_id` 在該學期資料中找不到（資料更新後下架、或連結被竄改）→ toast/提示「此課程連結可能已更新或不存在」。
- `term` 不在資料集 manifest → 同上提示。
- 逾時（資料載入失敗）→ 沿用既有資料載入錯誤處理；share 流程不另造錯誤路徑。

### 5. 元件 / 檔案
| 檔案 | 職責 |
|---|---|
| `lib/share/course-link.ts`（新） | `buildCourseLink({termKey, offeringId, origin})` / `parseCourseLink(searchParams)` 純函式 |
| `lib/share/share-course.ts` 或併入上檔（新） | `shareOrCopy(url, title)`：navigator.share → clipboard → 手動 fallback，回傳結果供 UI 顯示 toast |
| `components/ui/toast.tsx`（新） | 極簡 toast（單則、自動消失）；複製提示與失效提示共用。用 zustand 或 context 觸發 |
| `lib/planner/use-share-link.ts`（新） | 讀參數、切學期、資料就緒後開窗、失效提示、清 URL 參數 |
| `components/planner/CourseDetailDrawer.tsx`（改） | 標題列加分享鈕、呼叫 `shareOrCopy` |
| `components/planner/PlannerLayout.tsx`（改） | 掛 `useShareLink()` |

### 6. 測試
- `course-link.test.ts`：`build` → `parse` round-trip；缺參數、非法值回傳 null；term 含 `-` 正確還原。
- `use-share-link.test.ts`：給定 `?term&course` → 呼叫切學期 + 資料就緒後 `openDetail`；找不到 → 觸發提示、不呼叫 openDetail；無參數 → 不動作；不修改 draft-store。
- toast 基本渲染/自動消失。

### 7. 已知限制
- 無後端 → 連結貼到 LINE/IG **沒有每堂課預覽卡**（僅網站通用 OG）。需 rich preview 時另做動態 OG 服務（未來）。

## 驗收
- 桌面：資訊窗按分享 → 連結進剪貼簿 + toast；貼到新分頁 → 自動開該課資訊窗。
- 手機：按分享 → 原生面板；他人開連結 → 自動開資訊窗。
- 分享一堂**非目前檢視學期**的課：連結含該 term → 開啟後自動切到該學期並開窗；接收者原學期草稿不受影響。
- 失效課號連結 → 顯示提示、不白畫面。
- 收件端 `draft-store` 前後不變（除非他自己按排入）。
