# Web 排課器 M1 — 核心排課迴圈 設計 spec

> 狀態：設計定案待使用者審查（2026-06-13，已含 Codex gpt-5.5 審查修正，見文末）。下一步＝使用者過目 → writing-plans 產實作計畫。
> 依據：`docs/PRD.md`（產品需求；§4.1 P0、§6.1 流程、§10 規則分級、§14 驗收、附錄 A 里程碑切分）、`docs/DESIGN.md` §4.5、`docs/DECISIONS.md` D5/D8、`crawler/models.py`（資料契約）、`apps/web/README.md`。
> 範圍：P1 Web 的 **M1（3 里程碑的第一刀）**。M2（身分/階段分類）、M3（匯出/PWA/分享）見附錄 A，本 spec 不含。

## 目標
不登入、不選身分，就能走完核心排課迴圈：**搜尋 → 加入 → 看到課表成形 + 即時衝堂 + 學分**。命中 PRD §14 的 M1 子集驗收（時間解析、加入 300ms 更新、衝突明確指出、資料更新時間顯示）。

## M1 範圍（做 / 不做）
**做**：資料載入層（可切換來源、單一學期）、課程庫（search anything + 篩選）、⭐收藏/帶選清單、視覺化週課表、點格時段搜尋、衝堂偵測與顯示（同格多課＋志願序）、學分統計、課程詳細抽屜、localStorage 單份草稿、Liquid-Glass 設計系統地基。
**不做（留後）**：M2＝身分選擇、六類階段分類、限制原因分級、新生/學制學分上限；M3＝payload 匯出、分享連結、PWA/Service Worker 離線、多份草稿、ICS。

### 與鎖定決策的關係（刻意切分，非偏離）
- M1 是 **P1 的第一刀**；P1/M1/M2/M3 邊界對照見 `docs/PRD.md` 附錄 A。CLAUDE.md 把分類/匯出列在 P1、Web v1 含「Service Worker 快取（PWA、離線）」——這些**仍是目標**，只是 M1 刻意先不做、分到 M2/M3。
- **PWA/Service Worker / ETag / brotli / TTL 等頻寬規則屬 M3**；M1 僅靠瀏覽器原生 HTTP 快取，無離線。此為 milestone 取捨，**明確低於**鎖定的 Web v1 終態。
- **手刻搜尋（不引入 FlexSearch/Orama）是 M1-only 取捨**；DESIGN §4.5 的 FlexSearch/Orama 仍是日後選項（排序/UX 需要時換），介面已預留。

### 命名慣例（定案）
- **資料欄位/持久化型別一律 snake_case**（`offering_id`、`course_code`、`is_placeholder`、`term_key`…），與 `models.py`/v1 JSON/生成的 TS 型別一致，**app 內不另設 camelCase 轉換層**。TS 函式參數與區域變數仍依慣例用 camelCase（如 `getTerm(termKey)`）——只有「資料形狀」鎖 snake_case。
- 例外：**M3 的 handoff payload** 對 App 用 PRD §9 / DESIGN §4.6 的 `offeringId`（camelCase）——僅在匯出邊界轉換，M1 不涉及。

---

## 1. 技術棧與部署
- **Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + 自訂 Liquid-Glass 主題 + framer-motion**（D8 鎖定）。
- **靜態匯出**（`next.config` `output: 'export'`）→ 純 SPA、無 server runtime；部署 Cloudflare Pages，綁定時 Root directory 指 `apps/web`。所有資料 client-side fetch。
- **PWA / Service Worker 離線留 M3**；M1 只建 Liquid-Glass 設計系統地基（tokens、glass 元件、motion）。
- 套件管理：pnpm。`apps/web` 為獨立 Next app；型別由 `packages/schema` 提供（見 §2.4）。

## 2. 資料層

### 2.1 可切換資料來源
- `DataSource` 介面：`getManifest(): Promise<Manifest>`、`getTerm(termKey): Promise<TermBundle>`（catalog + periods + classes + enrollment）。
- 兩個實作：
  - `LocalDataSource` — 讀 `apps/web/public/data/v1/`（dev fixtures）。
  - `CdnDataSource` — fetch `NEXT_PUBLIC_DATA_BASE_URL`（prod＝`https://cdn.ntutbox.com/course/v1/`）。
- 由 env 選擇：`NEXT_PUBLIC_DATA_BASE_URL` 未設或指向 `/data/v1` → local；設為 CDN URL → cdn。**不把來源綁死在程式**，CDN 上線前也能完整開發（使用者決策）。
- **錯誤/重試狀態**：每次 fetch 有 `loading / ready / error` 三態；網路或解析失敗 → 顯示可重試錯誤卡（不靜默失敗）。**M1 不驗 sha256/size**（manifest 雖帶，但靜態 fetch 過度防禦，列為延後）；僅做 JSON parse 與最小 schema 健檢（缺必要檔→error）。
- `Manifest` / `TermBundle` 型別來自 `packages/schema`（§2.4）；URL 解析＝`base + manifest.terms[term].<file>.url`。

### 2.2 載入流程（單一學期）
1. `getManifest()` → 學期清單 + 每檔 sha256/size + `generated_at`。
2. 預設選最新學期（115-1）；`TermSwitcher` 可切，但**一次只載一個學期**。
3. `getTerm(termKey)` → 載 `catalog.json`（主目錄）+ `periods.json`（節次↔牆鐘）+ `classes.json`（班級清單，篩選用）+ `enrollment.json`（人數 overlay）。
4. 建搜尋索引（§3）。存入 term-store。
5. 顯示**兩個獨立時間戳**：catalog `freshness.catalog_crawled_at`（目錄結構）與 enrollment `observed_at`（人數快照），分開標示（PRD §14 驗收；人數較常過期，避免誤導）。

### 2.2.1 學期切換並發
- 切換學期時以**世代序號（generation token）**標記當前載入；fetch/建索引完成時若世代已過期 → **丟棄結果**（不更新 store），避免快慢回應交錯。
- 切換期間 UI 顯示載入態；草稿 **依 termKey 隔離**，切回原學期即還原。前一學期載入中再切走 → 取消/忽略其後續寫入。

### 2.3 dev fixtures
- 複製 `data/v1/` 的 115-1（+114-2 供切換測試）到 `apps/web/public/data/v1/`。fixtures 體積小、commit 進 repo 供本地與 CI 測試（非 production 資料源）。

### 2.4 型別單一真相（補 packages/schema 待辦）
- 新增 script：跑 `crawler/models.py` 的 `model_json_schema()` → `packages/schema/schema.json` → `json-schema-to-typescript` 生 `packages/schema/index.d.ts`。
- web 從 `packages/schema` import `CourseOffering` / `Catalog` / `Periods` / `Classes` / `Enrollment` 等型別，杜絕三端漂移（D4）。
- 人數 overlay merge 契約：catalog 純結構、`enrollment.json` 以 `offering_id` join 覆蓋（DESIGN infra spec「enrollment overlay merge」契約）。

## 3. 搜尋引擎（search anything + 篩選）

### 3.1 索引
- 載入學期時建記憶體索引：每課一條 normalize 後的 **search blob**，串接：`name.zh`、`name.en`、教師名、**`offering_id`（課號）**、**`course_code`（課程編碼）**、`unit_name`、班級名、`notes_raw`。
- `lib/search/normalize.ts`：轉小寫、去空白（解 pangu 加空白問題）、全形→半形。
- CJK **bigram** 計分（query 切 bigram，與課程 bigram 集合交集計分）+ 子字串 fallback。單一學期 ~2500 課 sub-ms，**M1 不引入 FlexSearch/Orama**（M1-only 取捨，見「與鎖定決策的關係」），手刻輕量、藏在 `search()` 介面後，需要再換。
- **排序規則（明定，避免實作時猜權重）**：① `offering_id`/`course_code` 完全相等 → ② 碼前綴相符 → ③ 課名完全/前綴相符 → ④ bigram 分數（高到低）→ ⑤ 同分以 `offering_id` 升冪 tie-break。
- **結果上限 + 虛擬化**：清單預設上限（如 200 筆）+ 虛擬捲動（react-virtual 之類）；超過上限顯示「縮小條件」提示，避免大結果集拖垮 300ms 更新目標。
- `search()` 介面支援 `signal`（AbortSignal）以配合學期切換取消。

### 3.2 篩選
- chips 多選：**星期 / 節次 / 學院 / 系所 / 班級 / 英文授課**。
- 組合邏輯：**跨類別 AND、同類別 OR**（例：(一 OR 三) AND 系所=資工 AND 英文授課）；文字 query 與篩選**疊加**同時生效。
- 資料來源：星期/節次＝`meetings[]`；系所＝`unit_code/unit_name`；班級＝`classes[]`（清單取自 `classes.json`）；英文授課＝`language`（EMI）。
- **英文授課定義**：`language` 視為 EMI 的值集明列於 `lib/filters/emi.ts`（如含「英」「English」「全英語」「英文授課」「中英」等 raw 值之白名單，逐學期可調）；非白名單一律不歸 EMI。
- **班級篩選含 pool/virtual 標籤**：`classes.json` 的 `kind`（regular/pool/virtual）在下拉中**標籤化呈現**（pool＝博雅/體育/英文池、virtual＝佔位）；M1 不做分類裁決（那是 M2），僅讓使用者看得出哪些是池班級。
- **學院**：目錄無此欄 → `lib/college-map.ts` 靜態表 `unit_code → 學院`（北科 ~7 學院；單一檔、含來源註解、逐學期校對）。選學院後系所清單只剩該院（連動）。**未對映的 `unit_code` 落 `未分類` 群組**，不報錯、不漏課。

### 3.3 時段範圍搜尋（點格）
- 同一 `search()` 引擎，隱含篩選 `day=D, period ∈ 該格 periods`；再疊 SlotPopover 內的系所/文字 query。

## 4. 狀態與草稿模型（三層）

```ts
// store/draft-store.ts — Zustand + persist middleware，localStorage 依 term_key 分鍵
TermDraft {
  schema_version: number                                 // 草稿格式版本（migration 用）
  term_key: string
  favorites: string[]                                    // ⭐收藏/帶選：offering_id（與排入獨立、去重）
  placed: { offering_id: string; priority: number }[]    // 排入課表（offering_id 去重）
}
```
- 三層：**課程庫**（全部，瀏覽面，非持久狀態）→ **⭐收藏/帶選**（觀望清單，不佔課表）→ **排入課表**（放進格子、可重疊、帶志願序）。
- **收藏與排入獨立**：一門課可只收藏、只排入、或兩者皆有。收藏只為快速回到該課（點開看詳情）。
- **志願序＝整數 `priority`**（1 最高）。衝堂格內相對順序由 priority 推導；SlotPopover 拖曳重排＝交換相關課的 priority。
  - **M1 範疇：priority 只是排課器內的排序**（給衝堂組挑第一志願）。匯出時的 phase/cunum 分組是 **M3** 的事，**不在 M1 假設可直接送 cwish**。
- **加入/去重/補洞規則**：`＋排入` 給 `priority = 現有最大 + 1`；同 `offering_id` 已在 placed → 不重複加入（no-op 或聚焦既有）；移除後 **priority 不強制重排**（容許空洞，排序只看相對大小），但提供「整理志願序」動作可壓實成連續整數。`favorites` 同樣去重。
- **陳舊草稿復原**：載入學期後，把 draft 的 `offering_id` 與當前 catalog join；**找不到的課**→標為「已失效」並從 grid 移除、列在提示區供使用者確認刪除（不靜默丟棄）；`schema_version` 不符 → 跑 migration 或安全清空並提示。
- 狀態管理：**Zustand**（draft 用 persist middleware）；term 資料（catalog/periods/classes/index）由 term-store 持有（載入一次）。

## 5. 衝堂與學分語意

### 5.1 衝堂偵測
- 兩門 placed 課的 `(day, period)` 集合有交集即衝堂（DESIGN：**只用 day×period 交集**，來源無單雙週/半學期，不假裝更高精度）。
- 建 `slot → placed[]` map；任一格 >1 課 → 衝堂格，標橘/紅。
- **衝堂組＝連通分量**：以「課程為節點、共享任一 slot 為邊」建圖，取連通分量（transitive）。例：A 與 B 衝在週一、B 與 C 衝在週三 → A/B/C 同一組。第一志願＝該組 priority 最小者。`lib/schedule/conflict.ts` 回傳分量清單供 grid 著色與學分計算共用。

### 5.2 衝堂顯示（已確認）
- **衝堂是刻意功能**（同格多課＝多志願），非錯誤。
- 桌機：**緊湊堆疊**，第一志願（priority 最小）橘底為主、後續志願只用小字課名疊下；**手機空間不足 → 退回只顯示第一志願 + 「+N」徽章**，點格展開全部。一般單課格不堆疊、正常顯示。
- 點格 → `SlotPopover`：頂部 search anything + 學院/系所/班級 chips、「已排入此格」可排志願序、「此時段其他可加入」每門帶 ⭐收藏 / ＋排入。
- **重排志願序的無障礙/觸控**：除拖曳外，每列提供**上/下移按鈕**（鍵盤可操作、觸控可靠）；拖曳僅為加速。一門課若跨多 slot 衝堂，於任一 slot 重排即調整其全域 priority（其他 slot 的相對序連動更新）。

### 5.3 學分統計（精確算法）
- 以 §5.1 的**連通分量**為單位：非衝堂課各自獨立（自成一組）；每組**只算第一志願**（priority 最小者）的學分。主數字＝「第一志願總學分」；附「排入總數」供參考。
- **排除條件＝僅 `is_placeholder`**（佔位課：notes 以「請選」開頭或 credit=0 無師資）。**真實 0.5 學分課照常計入**——不是「所有 0.5 都排除」，只排除佔位旗標課（DESIGN/CLAUDE：credit 用 decimal、加總排除佔位）。
- `credits` 為 null 的課以 0 計、並標記「學分未知」。重複 `offering_id` 已在 draft 層去重（§4），不會重複計分。
- 同時顯示衝堂數。**學制/新生 16–25 上限綁身分 → 留 M2**。

### 5.4 邊界情況
- **無時段課**（`meetings[]` 空，常見於研究所/專題）：**不佔課表格**；列在「無時段課程」獨立區塊，仍計入收藏/排入與學分（依 §5.3 規則）。
- **同 `course_code` 多 `offering_id`（同課多班）**：**允許**同時排入當備選（衝堂組會自然把同時段者歸一組排志願）；若多個 section 排在**不衝堂**時段 → 顯示**軟提示** info（「這幾門是同一課程的不同班」），不阻擋（分組裁決是 M2/M3）。
- **enrollment overlay 缺失/部分/無容量**：overlay join 不到該課 → 人數顯示「—」與「無資料」；`observed_at` 缺 → 不顯示人數時間戳；catalog 端 `capacity` 恆 null（DESIGN）→ 只顯示已選人數、不顯示「X/Y」比例。

## 6. 元件拆分

```
apps/web/
  next.config.ts (output:'export')、tailwind/postcss、tsconfig
  public/data/v1/…                      # dev fixtures（115-1 / 114-2）
  src/
    app/layout.tsx                       # 根：主題 provider、系統字體
    app/page.tsx                         # 單頁 planner（M1）
    components/planner/
      PlannerLayout.tsx                  # 桌機 B（課表主場+可收合課程庫）/ 手機 C（全幅課表+底部 sheet）響應式外殼
      WeeklyGrid.tsx                      # 週課表 grid（節次序讀 periods.json）
      TimetableCell.tsx                   # 空 / 單課 / 衝堂堆疊
      SlotPopover.tsx                     # 點格時段課程清單
      CourseLibrary.tsx                   # 右側面板(桌機)/底部 sheet(手機)
      CourseSearchBar.tsx                 # search anything 輸入
      FilterChips.tsx                     # 星期/節次/學院/系所/班級/英文 chips
      CourseList.tsx / CourseListItem.tsx # 結果清單（⭐ / ＋）
      CourseDetailDrawer.tsx              # 點課 → 抽屜（桌機右滑 / 手機底部全屏）；僅顯示 catalog.json 既有欄位
      FavoritesList.tsx                   # ⭐收藏/帶選清單
      CreditSummary.tsx                   # 學分 + 衝堂數（底部常駐 bar）
      TermSwitcher.tsx                    # 學期選擇
    components/glass/                     # GlassPanel / GlassCard…（Liquid-Glass 原語）
    components/ui/                        # shadcn 元件
    lib/data/{datasource,local-datasource,cdn-datasource,index}.ts
    lib/search/{normalize,build-index,search}.ts
    lib/schedule/{conflict,credits,periods}.ts
    lib/college-map.ts
    store/{term-store,draft-store}.ts
    styles/globals.css（theme tokens）
  packages/schema/（root）：generated index.d.ts + schema.json
```

## 7. 資料流（核心迴圈）
1. 載入 → `getManifest` → 學期清單 → 預設最新 → `getTerm` → 建索引 → term-store。
2. 課程庫搜尋/篩選 → 結果清單。
3. ⭐收藏 → `draft.favorites`；＋排入 → `draft.placed`（給預設 priority＝目前最大+1）。
4. `WeeklyGrid` 由 `conflict.ts` 的 slot map 把 placed 課渲染進格子；衝堂格上色。
5. 點格 → `SlotPopover`：時段範圍搜尋 + 已排志願（拖曳改 priority）+ 可加入。
6. `CreditSummary` 重算（衝堂組取第一志願、排除佔位）。
7. draft 依 termKey persist 到 localStorage。

## 8. Liquid-Glass 設計系統地基（最小集，只服務 planner 畫面）
- **僅做 planner 用到的最小集**，不做泛用 UI 系統（避免無限擴張）：
  - tokens：blur、半透明度、tint、radii、系統字體棧（`-apple-system, …`）、light/dark。
  - 原語：`GlassPanel`（課程庫/側欄）、`GlassCard`（課程卡/詳情）、`GlassBar`（底部學分 bar）、sheet/drawer/popover 的玻璃容器。
- `components/glass/` 包 shadcn + `backdrop-filter`；framer-motion 做 sheet/drawer/popover 轉場。
- **尊重 `prefers-reduced-transparency` / `prefers-reduced-motion`** → 不透明 / 無動畫 fallback（D8）。

## 9. 測試（TDD）
- **Vitest + React Testing Library**。
- 單元：`normalize`、`search/filter`（search anything 跨欄、AND/OR 組合、時段範圍、**排序規則 tie-break**）、`conflict`（day×period 交集、多 meeting、**連通分量含 transitive**）、`credits`（第一志願、僅排除 `is_placeholder`、真 0.5 計入、credits=null、去重）、`periods`（N/A–D 排序）、`college-map`（含**未對映→未分類** fallback）、`datasource`（fixture 解析 + enrollment overlay merge + **缺失/部分 overlay**）。
- 互動：加入/收藏（去重、no-op 重複加入）、衝堂堆疊渲染（桌機/手機 fallback）、SlotPopover 重排志願序（**拖曳 + 上下移按鈕/鍵盤**）、CourseDetailDrawer、無時段課區塊。
- **失敗/規模/競態**：陳舊草稿復原（offering 消失/`schema_version` 不符）、部分資料載入失敗→error 卡、**學期切換競態**（過期世代丟棄）、結果清單效能（上限/虛擬化）、**300ms 更新在大結果集下達標**。

## 10. 驗收（PRD §14 的 M1 子集）
- [ ] 課程時間解析正確顯示（含多節、跨星期、N/晚上節次）。
- [ ] 搜尋結果點擊後 300ms 內更新週課表。
- [ ] 衝堂時明確指出衝突課程與時段（橘/紅 + SlotPopover 列出）。
- [ ] search anything 能以 課名/教師/課號/課程編碼 任一找到課。
- [ ] 篩選（星期/節次/學院/系所/班級/英文）跨類別 AND、同類別 OR 正確。
- [ ] 前端清楚顯示資料來源與最後更新時間。
- [ ] 草稿（收藏 + 排入 + 志願序）重整後從 localStorage 還原。

## 11. 明確排除（YAGNI / 留後）
- 身分選擇、階段分類、限制原因分級、學分上限（M2）。
- payload 匯出、分享連結、PWA/SW 離線、多份草稿、ICS（M3）。
- 跨學期搜尋（一次一學期）。FlexSearch/Orama（手刻夠用再說）。後端 / 帳號同步（D5 否決）。

## 12. 建置順序（給 writing-plans 的種子）
1. `apps/web` Next 靜態匯出骨架 + Tailwind + shadcn + Liquid-Glass tokens。
2. `packages/schema` 型別生成 script；web import 型別。
3. 資料層（DataSource + local fixtures + manifest/term 載入）+ term-store。
4. 搜尋引擎（normalize/index/search）+ 篩選 + college-map。
5. WeeklyGrid + TimetableCell + periods 排序（先讀-only 渲染 placed）。
6. draft-store（收藏/排入/priority）+ CourseLibrary/List/Item 的 ⭐/＋ 動作。
7. conflict + 衝堂格顯示（桌機堆疊/手機 fallback）+ SlotPopover（時段搜尋+拖曳志願）。
8. credits + CreditSummary。
9. CourseDetailDrawer、TermSwitcher、RWD（桌機 B / 手機 C）收尾。
10. 驗收 §10 逐項過。

---

## 待補資料 / 風險
- **`college-map.ts`**：需建一張 `unit_code → 學院` 靜態表（北科 ~7 學院）；來源非目錄、手動整理一次、檔內註明來源與校對日；未對映 `unit_code` 落 `未分類`、逐學期校對。屬內容分類工作、非純 UI plumbing。
- **`requirement.category` 多為 unknown**：課程標準（Cprog）未爬 → 「必修/選修」篩選 M1 不可靠，故 M1 篩選**不含修別**（留待標準補抓後）。
- **欄位命名一致性**：v1 JSON 與 `models.py` 採 **snake_case**（`offering_id`/`is_placeholder`）；DESIGN 內文偶寫 camelCase 僅為敘述，**以生成的 schema 為準**。
- **enrollment 陳舊/缺失**：人數為快照、選課季會動；M1 顯示 `observed_at`、缺資料顯示「—」、不作即時可選性判斷（那是 App live 的事）。
- **115-1 資料**：catalog 已存在（2440 課）；以此為 M1 預設學期。

## Codex 審查修正紀錄（2026-06-13，gpt-5.5）
Codex 審查（design review）幾乎全數採納——多為「契約收緊」而非重新設計。逐項處置：
1. **狀態模型/命名**：draft 全面 snake_case（`offering_id`/`is_placeholder`）、加 `schema_version`；新增「命名慣例」段（snake_case 貫穿，僅 M3 匯出邊界轉 camelCase）。（§命名慣例、§4）
2. **priority 去 scope-creep**：移除「M3 匯出直接用」；明定 priority 為 M1 排課器排序，phase/cunum 分組屬 M3。（§4）
3. **衝堂組＝連通分量**（transitive）；學分按連通分量取第一志願、**僅排除 `is_placeholder`**（真 0.5 計入）、credits=null 計 0。（§5.1、§5.3）
4. **邊界情況**新增 §5.4：無時段課獨立區、同 course_code 多 offering 軟提示、enrollment overlay 缺失顯示。
5. **加入/去重/補洞 + 陳舊草稿復原**規則明定（offering 消失→標失效、`schema_version` 不符→migration/清空）。（§4）
6. **規模/錯誤/競態**：CourseList 結果上限+虛擬化、`search()` 支援 AbortSignal、學期切換世代序丟棄、DataSource 三態錯誤、**M1 不驗 sha256**（列延後）。（§2.1、§2.2.1、§3.1）
7. **搜尋排序規則**明定（精確碼>前綴>課名>bigram>tie-break）；**英文授課**值集明列。（§3.1、§3.2）
8. **班級篩選標籤化 pool/virtual**；學院未對映→未分類 fallback。（§3.2）
9. **CourseDetailDrawer 限 catalog 既有欄位**（描述/課綱未爬，不拉進 M1）。（§6）
10. **兩個時間戳**（catalog `crawled_at` / enrollment `observed_at`）分開顯示。（§2.2）
11. **刻意切分聲明**：PWA/SW、FlexSearch 為「低於鎖定 Web v1 的 M1 取捨」，邊界對照 PRD 附錄 A。（§與鎖定決策的關係）
12. **Liquid-Glass 最小集**（只服務 planner 畫面、列出原語）。（§8）
13. **拖曳志願序無障礙**：補上下移按鈕/鍵盤、跨多 slot 連動。（§5.2）
14. **測試**補：陳舊草稿、部分載入、學期切換競態、結果清單效能、300ms 大結果集、拖曳 a11y。（§9）

保留（使用者已決策）：`college-map`/學院篩選保留（最小化+未分類 fallback）；`TermSwitcher` 保留但 UX 期待設在「單一學期載入」。
