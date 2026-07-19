# 微學程功能設計（瀏覽＋分類＋規則原文）

> 2026-07-19 brainstorming 定案。背景調查結論見 `docs/research/2026-07-19-mprogram.md`。
> 範圍決策：三選一選了「瀏覽＋分類＋規則原文」；入口選了「CourseLibrary 新分頁」；資料管線選了「單一 mprograms.json」。

## 目標與動機

112 學年度起入學的日間部大學部學生，畢業前須完成「跨領域學習」（微學程／一般學程／第二專長／輔系／雙主修，五選一；學則第 48 條第 5 款）。微學程（8–12 學分）是最輕量路徑，但學校系統對它的呈現破碎：課程清單在課程系統、修讀規則在教務處 PDF、本學期開課要自己交叉查。本功能讓學生在排課器裡**以學程為中心**瀏覽：看分類課程清單、看本學期開了什麼、直接排入課表、讀規則原文。

**成功標準**：學生不離開排課器就能（1）挑一個自己可修的微學程（2）知道基礎/核心/總整各有哪些課、這學期開了哪些班（3）把課排進課表（4）讀到修讀規則與教務處入口。

## Non-goals（明確不做，記錄原因）

- **`/programs` 獨立 SEO 頁**：下一個 PR 候選（呼應分享連結長尾策略），本 PR 只做面板內體驗。
- **PDF 結構化與「湊齊了沒」進度檢查**：維持「Web 不做畢業學分計算」的既有決策；且排他資格/逐類學分等規則句型不一，結構化需人工校對 48 份 PDF，邊際價值低（詳研究文件）。
- **跨校/聯盟課程**（北大課號、AI 聯盟課）：不在本校課程系統、無 course_code，無法呈現；由教務處連結兜底。
- **gnehs 修復 PR**：另外處理（regex 吃內容 bug 的 root cause 已在研究文件記錄）。

## §1 資料層（crawler / schema / pipeline）

### Model（`crawler/models.py`）

- 新增 `MicroProgramCourse`：
  - `course_code: str`、`name_zh: str`、`credits: Decimal`
  - `category: Literal["基礎","核心","總整","進階","應用"] | None`（正規化後；無法辨識 → `None`）
  - `category_raw: str | None`（Cprog notes 欄原文保底，如 `＊`、`核e`）
  - `emi: bool = False`（notes 中的 `e` 標記拆出）
- `MicroProgram` 加欄位：`courses: list[MicroProgramCourse] = []`、`rules_text: str | None = None`（「相關規定」純文字，保留換行，**不解析內容**）。`offering_ids` 保留不動。
- `SCHEMA_VERSION` 為全域常數（所有 artifact 共用）→ 遞增前確認 web 端讀取為寬鬆容錯（實作時驗證；若 web 有嚴格等值檢查，改為向後相容處理）。

### 爬蟲（`crawler/ntut_catalog/programs.py`、`parse_program.py`）

- `crawl_mprograms(client, term_key)` 擴充：既有 SearchMProgram 流程外，對每學程抓 `Cprog.jsp?format=-4&year=<Y>&matric=H&division=<code>`，其中 `<Y>` = term 的學年（115-1、115-2 皆為 115）。每學期 +46 請求，沿用 client 既有節流。
  - 課程清單：**重用既有 `parse_cprog_standard`**，再映射成 `MicroProgramCourse`。
  - 新增 `parse_cprog_rules(html) -> str | None`：抓課程表格**之後**的單格 `<td><font>` 區塊，`<br>`→換行、去 tag、unescape。定位用**結構特徵**（課程表格後、含長文字的單格 table），**禁用 nth-child 索引**（gnehs 教訓）。找不到 → `None`，不丟例外。
- notes → category 正規化：已知 8 變體 `基礎/核心/總整/進階/應用/＊/核e/e基`。`e` 疑似 EMI 標記黏連——**實作時開 2+ 個 live 頁實證 `e` 的語意再寫映射**，不猜。規則：拆出 `e` → `emi=True`；餘字前綴映射（基→基礎、核→核心、總→總整）；映不出 → `category=None` + 保留 `category_raw`。
- 解析防呆沿用 repo 慣例：html5lib、表頭定位、缺欄 → null 不回退預設值。

### Pipeline

- `write_mprograms` / artifacts v1 複製 / `infra/publish.py` / manifest 均已存在，不動。
- **`.github/workflows/crawl.yml`（每日 cron）補跑 `crawl-mprograms`**——現有 `data/canonical/115-1/mprograms.json` 是 2026-06-14 手動一次性產物，目前 cron 不會更新它。

## §2 Web 資料層（`apps/web`）

- 新 hook `use-mprograms`：切到微學程 tab 才 **lazy fetch** `v1/terms/<term>/mprograms.json`（不增首屏 payload），快取＝hook 內記憶體 cache（web 目前尚無 Service Worker；PWA 為既有 roadmap 項）與 CORS 前提（資料在 cdn.ntutbox.com）。
- TS 型別：`packages/schema` 重新生成（Pydantic → schema.json → index.d.ts）。
- 反查索引：由 mprograms 建 `Map<offering_id, MicroProgram[]>` 供課程詳情 badge 用。catalog 的 `interdisciplinary`（models.py:314，inline 學程名原文）**僅交叉核對、不當資料源**（對不出學程代碼）。

## §3 UI（遵循 `apps/web/AGENTS.md` 設計規範：共用元件、glass token、圓角級距）

- **入口**：`ui-store` 的 `libraryTab` 擴成 `"courses" | "favorites" | "programs"`，另加 `selectedProgramCode: string | null`（list ↔ detail 切換、供 Drawer badge 跳轉用）；`PlannerLayout` PanelTab 加「微學程」（桌面右面板與行動 sheet 共用機制）。
- **`MicroProgramList`**（tab 首層）：46 學程清單，每列＝學程名＋本學期開課班數；頂部 `SearchInput`（variant=inset）前端過濾（不進 bigram 索引）。列表底部放教務處微學程專區連結（涵蓋未進系統的學程）。
- **`MicroProgramDetail`**（同面板 drill-in，含返回）：
  - 頂部 context copy 一句：「112 學年度起入學之日間部大學部，畢業前須完成跨領域學習（微學程為五種路徑之一）；修讀須於教務處公告期間登記。」
  - **分類課程清單**：依 基礎/核心/總整（/進階/應用）分組；每課顯示課名、學分；EMI 不渲染（e 注記語意未確證，僅存資料層；見計畫附錄 A）；本學期有開 → 班級 chips（FilterChip 樣式）可點 → 開 `CourseDetailDrawer` 排入；未開 → 灰態「本學期未開」。
  - **規則原文**：`rules_text` 以 `whitespace-pre-line` 摺疊區塊呈現；固定外連「完整規定與課程規劃書（教務處微學程專區）」——連專區入口頁，**不做逐學程 PDF 對映**（URL 不穩定）。
- **`CourseDetailDrawer`** 加「屬於：XX 微學程」chips（反查索引）；點擊 → 切到 programs tab 並開該學程 detail。

## §4 邊界與錯誤處理

| 情況 | 行為 |
|---|---|
| `rules_text = None`（來源改版/解析失敗） | 顯示「規定原文暫缺，請以教務處專區為準」＋連結；不留空白、不編造 |
| 學程課程本學期無班 | 灰態呈現（誠實資料缺口） |
| `offering_ids` 反查不到 catalog 課 | 顯示課號純文字（防呆，理論上不發生） |
| mprograms.json fetch 失敗 | tab 內錯誤狀態＋重試鈕，不影響其他 tab |
| 教務處有、系統沒有的學程（48 vs 46） | 無法列出；由列表底部與 detail 的教務處連結兜底 |

## §5 測試與驗收

- **crawler**：`parse_cprog_rules` 以 AV2 live HTML 為 fixture；category 正規化 8 變體全覆蓋；`crawl_mprograms` mock client 整合測試。實爬 115-1 全 46 學程過 model 驗證、46/46 與 SearchMProgram 對齊。
- **web**：`MicroProgramList` / `MicroProgramDetail` / 反查索引 各自 `*.test.tsx`（沿用既有慣例）。
- **視覺驗收**：本地＋preview 部署截圖（桌面/行動 × light/dark），照 UI 驗收慣例；對比與資料缺口誠實呈現為驗收項。
- **實作時待驗證清單**：① notes `e` 標記語意（live 實證）② td「相關規定」與 PDF 詳略差異抽查 3–5 個學程 ③ 全域 `SCHEMA_VERSION` 遞增對 web 讀取的影響。

## §6 PR 打包

- 分支：`feat/mprogram`（worktree `../ntutbox-course-mprogram`），PR 進 main，不直推。
- 內容：crawler 擴充＋web UI＋`crawl.yml` 補 cron 步驟＋docs（本 spec、`docs/research/2026-07-19-mprogram.md`、DESIGN.md 補 mprograms v2 schema、CLAUDE.md「現況」段修正——微學程/課程標準/課程詳情已爬）。data 產物走 data branch/CI（main PR 不含資料）；merge 後以 workflow_dispatch 觸發 crawl.yml 重爬並發佈 R2。
- 公開 repo 守則：不得含學生個資（學號/cunum/帳密/session）。學程聯絡教師姓名/email 屬學校公開發布的機構聯絡資訊，**非**守則所指個資——`rules_text` 照原文保存並隨 artifact 公開發佈；docs 引例時省略 email 僅為避免餵 spam 爬蟲，非硬性要求。
