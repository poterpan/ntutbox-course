# PRD — 北科盒子排課系統技術文件 v0.1

> **這是什麼**：產品需求文件（《北科盒子排課系統技術文件 v0.1》，2026-06-13）的 markdown 轉換版，供 AI session 快速閱讀。
> 原始檔：`docs/北科盒子排課系統技術文件.docx`（同目錄）。本檔由該 docx 以 pandoc 轉出後手動整理 callout / code 區塊。
> **權威性**：本文＝**產品需求來源**。但部分技術細節已被 `docs/DESIGN.md`（§4.5/§4.6）修正/超越——衝突時以 DESIGN.md / `crawler/models.py` 為準。對照表見 `docs/PRD.md` 末「附錄 A」與 brainstorm spec。

---

**北科盒子排課系統技術文件**

Web/PWA 排課規劃器 × 北科盒子 App 選課執行器

版本：v0.1 \| 日期：2026-06-13 \| 對象：北科盒子產品與工程規劃

> **文件摘要**
>
> 本文件整理北科盒子排課系統的產品定位、分階段上線策略、北科大選課制度特化需求、功能優先級、技術架構、資料模型、Deep Link 匯入格式、風險與驗收標準。建議第一階段先讓 Web/PWA 排課規劃器與北科盒子 App 手動選課功能分開上線，待兩側穩定後再以選課計畫 payload 串接。

# 1. 背景與結論

你的規劃是合理的：第一階段先讓「公開排課規劃系統」與「北科盒子 App 內選課功能」各自穩定上線，避免同時承擔查課、排課、登入、送件、錯誤回寫與跨系統狀態同步的風險。等兩邊資料模型與使用流程穩定後，再透過 Universal Link / URL Scheme 匯入一份結構化的選課計畫，讓 App 進行正式送件。

> **建議產品定位**
>
> 北科盒子 Planner 是一個給北科學生使用的排課規劃器，能在 Web/PWA 上公開查課、排課、即時檢查衝堂與學分限制，並自動區分「期末網路初選」、「開學後加退選」與「僅供規劃」課程；北科盒子 App 則負責登入、送件、結果回寫與日常課表體驗。

| **層級** | **目的** | **第一階段做法** | **後續整合方向** |
|----|----|----|----|
| Web/PWA Planner | 公開查課、排課、比較、儲存草稿 | 不需要登入即可使用；以 localStorage / shareable plan 起步 | 產生標準化選課計畫 payload，導入 App |
| 北科盒子 App | 課表顯示、同步、教材、Widget、Dynamic Island、手動選課 | 先提供 App 內手動選課與選課結果同步 | 接收 Web payload，協助批次送件與結果回寫 |
| 學校選課系統連接層 | 對接期末網路初選、開學後加退選、新生系統 | 先穩定支援你已驗證的前兩個系統 | 新增新生系統、錯誤原因翻譯、重試與節流機制 |

# 2. 參考資料與制度事實

本文件使用以下公開來源作為制度與技術設計依據；北科課程好朋友的定位與不足，主要依使用者已提供的產品觀察整理，尚未找到足夠完整且可引用的官方公開規格。

| **來源** | **可確認資訊** | **設計影響** |
|----|----|----|
| 北科大課程系統 | 公開入口包含課程概述、課程查詢、上課時間表、教師授課時數表、教室使用情形、學程與微學程查詢等。 | Planner 可將官方資料重新組織為「排課決策」導向，而非只做入口集合。 |
| 北科大教務處新生選課說明 | 新生預選與全校加退選分屬不同時段；新生預選限選本班課程；跨系班修讀須於開學前兩週加退選期間辦理；系統會對衝堂與最高學分限制警告並阻擋選入。 | 必須建立選課階段分類、限制原因、錯誤與警告分級。 |
| MDN PWA 文件 | PWA 可用同一份 Web codebase 跨平台運行、可安裝、可離線與背景操作，並可與裝置及其他 App 整合。 | 排課規劃層適合用 Web/PWA 做公開低門檻入口。 |
| MDN Service Worker API | Service Worker 可攔截網路請求、快取資源、支援離線體驗，且需要 HTTPS 安全環境。 | 課程資料、排課草稿與靜態資源可支援離線或弱網路場景；正式登入與送件仍應放在 App。 |
| Apple Developer 文件 | Apple 提供 Universal Links 與 Custom URL Scheme 文件，但頁面內容需 JavaScript 才能完整顯示。 | 整合時仍建議以 Universal Link 優先，URL Scheme 作 fallback。 |

# 3. 分階段上線策略

| **階段** | **目標** | **範圍** | **不做事項** | **驗收標準** |
|----|----|----|----|----|
| Phase 0：資料與 POC 穩定 | 穩定取得課程資料與選課系統互動流程 | 課程資料 normalize；期末網路初選與開學後加退選接口測試；建立測試帳號情境 | 不做公開批次送件；不承諾新生系統可用 | 能準確解析課程時間、教室、開課班級、學分與系所欄位；選課請求可被重放測試 |
| Phase 1：雙系統分開上線 | Web 做排課；App 做手動選課 | 公開 Planner；App 手動選課；App 課表同步；錯誤訊息可讀化 | Web 不直接登入學校系統；Web 不代送選課 | 使用者能在 Web 完成課表草稿；App 能獨立完成已支援系統的選課流程 |
| Phase 2：Plan 匯入 App | Web 產生選課計畫，App 接收並顯示確認頁 | Universal Link / URL Scheme；payload schema；App 確認頁；送件前重新檢查 | 不做完全自動背景送件 | Web 產出的同一份 plan 可在 App 還原課表與階段清單 |
| Phase 3：半自動送件與回寫 | App 依階段送件並回寫結果 | 批次送件；失敗原因翻譯；學校系統狀態查詢；正式課表同步 | 避免高頻自動 retry 造成系統負載 | 每門課有送件結果：成功、失敗、待處理、需手動處理 |
| Phase 4：進階決策輔助 | 提高選上率與規劃品質 | 候補/替代課推薦；畢業學分追蹤；評價/心得；行事曆與通知策略 | 不以甜涼度作為唯一排序 | 能幫學生回答：現在該選哪門、要等哪個階段、替代方案是什麼 |

# 4. 功能需求分級

## 4.1 必要功能（MVP）

| **功能** | **說明** | **實作重點** | **優先級** |
|----|----|----|----|
| 課程搜尋與篩選 | 依課名、教師、系所、年級、時間、學分、通識/博雅、英文授課等條件查找課程。 | 索引欄位要 normalize；搜尋要支援中英文、空白、教師姓名與課號。 | P0 |
| 視覺化週課表 | 點選課程後即時加入週課表，顯示時間、教室、教師與課名。 | 手機版要避免過密，可用日視圖/週視圖切換。 | P0 |
| 衝堂檢查 | 加入課程時即時提示與哪些課、哪個時段衝突。 | 時間解析要支援多時段課、實習課、隔週課或特殊時段。 | P0 |
| 學分統計 | 顯示總學分、各類別學分與可能的最高/最低學分限制。 | 新生規則要特別顯示 16-25 學分限制；一般生規則需後續補全。 | P0 |
| 選課階段分類 | 每門課自動標示「初選可送」、「加退選可送」、「僅供規劃」、「不可送」。 | 依學生班級/系所/年級與開課班級判斷；不可判斷時標示未知而非亂猜。 | P0 |
| 限制原因顯示 | 不能只 disable；要告訴使用者為什麼不能在該階段送。 | 例：跨系班需等加退選、衝堂、超學分、新生系統未驗證。 | P0 |
| 草稿儲存 | 在 Web 端儲存課表草稿。 | 第一版可 localStorage；之後再做帳號同步。 | P0 |
| 匯出/分享 | 匯出 JSON、分享連結或導入 App。 | payload 要有版本號與學期資訊，避免未來 schema 破壞相容。 | P0 |

## 4.2 可選功能（穩定後加入）

| **功能** | **價值** | **注意事項** | **建議時機** |
|----|----|----|----|
| 登入同步草稿 | 跨裝置繼續排課，Web 與 App 可同步。 | 需處理個資、權限與刪除資料機制。 | Phase 2 後 |
| ICS / Google Calendar 匯出 | 延伸北科盒子既有課表同步價值。 | 正式選上前應標記為「暫定課表」。 | Phase 1 |
| 替代課推薦 | 衝堂或額滿時快速找相同課名、同類型博雅、同教師不同班。 | 需要課程分類與相似度模型，不宜第一版硬做。 | Phase 3 |
| 課程評價/心得 | 幫助決策，提升回訪率。 | 需避免誹謗、個資、灌票與偏誤；應設審核與檢舉。 | Phase 4 |
| 畢業學分追蹤 | 長期價值高，可黏住大二以上學生。 | 需完整課程標準、抵免、雙主修/輔系/學程規則；複雜度高。 | Phase 4 |
| 多人共排/分享課表 | 社交與同學揪課需求。 | 要避免公開個人課表造成隱私風險。 | Phase 4 |

## 4.3 加分功能（差異化）

| **功能** | **為什麼加分** | **實作建議** |
|----|----|----|
| 階段化選課清單 | 北科有初選、加退選、新生系統差異；自動分類能直接降低學生認知負擔。 | 在課表旁常駐顯示三個清單：初選可送、加退選再送、僅規劃。 |
| App 送件前確認頁 | 降低誤送風險，也讓使用者理解 Web 與 App 分工。 | 顯示課程、階段、限制、預期結果與「不送出只保留」選項。 |
| 錯誤訊息翻譯器 | 官方系統錯誤往往偏技術或行政語言，翻譯成行動建議很有價值。 | 建立 errorCode / errorPattern 對應表：原始訊息、原因、使用者下一步。 |
| 北科特殊規則提示 | 能讓產品不像通用查課器，而是真的懂北科。 | 博雅志願、英文分班、跨系班加退選、新生限制都用資訊卡提示。 |
| Dynamic Island / Widget 延伸 | 你的 App 已具備日常課表優勢，整合後能從選課延伸到上課當天。 | 未正式選上前用「暫定」標籤；成功後才進正式 Widget。 |

# 5. 北科大特別需要注意的規則與 UX

| **規則/情境** | **產品處理方式** | **UI 文案建議** | **風險** |
|----|----|----|----|
| 期末網路初選只能選本班課程 | 依學生班級與課程開課班級自動分類；非本班課放入加退選清單。 | 「此課非本班課程，建議先保留於課表，開學後加退選再處理。」 | 班級欄位解析錯誤會造成誤判。 |
| 開學後加退選可跨系班修讀 | 跨系/跨班課程不阻擋排入，但預設不列入初選送件。 | 「可規劃，但不屬於初選可送範圍。」 | 實際仍可能受人數、先修、系所限制。 |
| 新生系統尚未驗證 | 保留 freshman phase，但標示 Beta/未驗證；不開正式送件。 | 「新生送件流程尚未完整驗證，目前僅支援規劃。」 | 不可假裝支援，避免新生錯過選課。 |
| 博雅課程採志願選填 | 不要只當成普通課程加入；需做志願排序清單與分發結果待回寫。 | 「博雅課程可能採志願分發，請依系統規則排序。」 | 志願分發結果與排課草稿可能不一致。 |
| 英文能力分班課程 | 顯示資訊提醒，不鼓勵使用者手動重複排入。 | 「此類課程可能由系統於開學後匯入。」 | 需依年度與系所例外條件更新。 |
| 衝堂與最高學分限制 | 作為 blocking error；在 Web 就先提示，App 送件前再檢查一次。 | 「此組合目前無法送出：與 X 課程週三第 5-6 節衝堂。」 | Web 判斷與官方系統可能不同，需以送件前結果為準。 |

# 6. 操作流程與 UI/UX 建議

## 6.1 Web/PWA Planner 流程

**流程**：進入網站 → 選擇學期 → 選擇身分/系所/班級 → 搜尋課程 → 加入模擬課表 → 即時檢查衝堂/學分/階段 → 儲存草稿 → 匯出/導入 App

- 首次使用不要強迫登入；先讓學生完成一次「看到課表成形」的成功體驗。

- 身分資訊不必一開始完整輸入，可以先選「系所 / 年級 / 班級」，用於初選可送判斷。

- 課程卡片需同時顯示「加入課表」與「此課在哪個階段可處理」。

- 右側或底部常駐顯示「初選清單」、「加退選清單」、「僅規劃清單」與警告數。

- 每一個警告都要能點擊定位到課表上的衝突區塊。

## 6.2 App 手動選課流程

**流程**：App 選擇選課系統 → 登入/驗證 → 搜尋或輸入課號 → 加入送件清單 → 使用者確認 → 送出 → 顯示結果 → 同步課表

- 第一階段先讓 App 選課功能獨立可用，避免 Web payload 還沒穩定就綁死 App 流程。

- 送件結果必須逐門課回報，不應只顯示「成功/失敗」。

- 保留學校系統原始回應，另提供使用者可理解的「原因」與「下一步」。

- 若 App 偵測到課表變更，應能回寫到課表、Widget、Dynamic Island 與教材入口。

# 7. 技術架構建議

| **模組** | **職責** | **建議技術/資料** | **備註** |
|----|----|----|----|
| Course Ingestion | 抓取/整理官方課程資料 | Python scraper / parser；排程；資料版本化 | 來源欄位需保存 raw data，方便 debug。 |
| Course Normalizer | 統一課程、教師、時間、教室、系所、班級、學分欄位 | Python 或 TypeScript shared schema | 這是整個系統最重要的品質基礎。 |
| Planner Web/PWA | 查課、排課、衝堂、學分、階段分類 | Next.js / Nuxt / SvelteKit 均可；IndexedDB/localStorage | 需支援手機與桌面。 |
| Rule Engine | 判斷衝堂、學分、階段、限制 | 可先在前端實作，之後抽成 shared package | App 送件前也要執行一次。 |
| Plan Exporter | 產生選課計畫 payload | JSON schema + base64url / signed token | payload 需版本化。 |
| App Executor | 登入學校系統、送件、查詢結果、同步課表 | iOS native + Python/Swift networking logic 規劃 | 避免在 Web 暴露帳密或 session。 |
| Sync Backend（可選） | 跨裝置儲存草稿、回寫結果 | PostgreSQL / Supabase / Firebase / self-hosted API | 可延後，不必 MVP 就做。 |
| Observability | 記錄資料抓取、規則判斷、送件錯誤 | Structured logs、Sentry、匿名事件 | 選課高峰期必備。 |

> **架構原則**
>
> 正式送件與登入流程應留在 App 或受控後端，不建議讓公開 Web 直接處理學校帳密。Web/PWA 專注於「公開、快速、可分享、低風險」的規劃體驗；App 專注於「個人化、登入、送件、同步與通知」。

# 8. 核心資料模型

> ⚠️ 此為技術文件 v0.1 的草案型別。實作以 `crawler/models.py`（Pydantic）為準：`Course`→`CourseOffering`（`offering_id`/`course_code`/`classes[]`/`requirement`/`meetings[]`）、`openClass?`→`classes[]` 陣列、phase 擴成六類（見附錄 A）。

```typescript
Course {
  id: string
  semester: string
  courseNo: string
  classNo?: string
  name: string
  teacherNames: string[]
  credits: number
  department: string
  openClass?: string
  category?: 'required' | 'elective' | 'liberal' | 'english' | 'program' | 'unknown'
  schedules: ScheduleSlot[]
  capacity?: number
  raw: object
}

ScheduleSlot {
  weekday: 1 | 2 | 3 | 4 | 5 | 6 | 7
  periods: string[]
  startTime?: string
  endTime?: string
  location?: string
  weekPattern?: 'weekly' | 'odd' | 'even' | 'unknown'
}

StudentContext {
  department: string
  grade?: number
  classCode?: string
  isFreshman?: boolean
  program?: string
}

PlanCourse {
  courseId: string
  desiredAction: 'add' | 'keep' | 'remove'
  phase: 'preselection' | 'add_drop' | 'freshman' | 'planning_only' | 'unknown'
  priority?: number
  warnings: RuleWarning[]
}

RuleWarning {
  level: 'error' | 'warning' | 'info'
  type: 'time_conflict' | 'credit_limit' | 'phase_limited' | 'freshman_unverified' | 'unknown_rule'
  message: string
  relatedCourseIds?: string[]
}
```

# 9. Web 匯入 App 的 payload 設計

> ⚠️ 此為技術文件 v0.1 草案。實作以 DESIGN.md §4.6 的 payload（`crawler/models.py` 的 `PlanPayload`）為準：`courseId`→`offeringId`、加 `datasetVersion`、`system` 值改 `cwish`/`oads`、phase 擴成六類。

```jsonc
{
  "version": 1,
  "school": "ntut",
  "semester": "115-1",
  "source": "ntutbox-planner-web",
  "createdAt": "2026-06-13T12:00:00+08:00",
  "studentContext": {
    "department": "資訊工程系",
    "grade": 2,
    "classCode": "四資二甲"
  },
  "plans": [
    {
      "phase": "preselection",
      "system": "term_end_preselect",
      "courses": [
        { "courseId": "COURSE_A", "action": "add", "priority": 1 }
      ]
    },
    {
      "phase": "add_drop",
      "system": "semester_add_drop",
      "courses": [
        { "courseId": "COURSE_B", "action": "add", "reason": "cross_department" }
      ]
    },
    {
      "phase": "planning_only",
      "courses": [
        { "courseId": "COURSE_C", "action": "keep", "reason": "time_conflict" }
      ]
    }
  ],
  "warnings": [
    {
      "level": "warning",
      "type": "phase_limited",
      "courseId": "COURSE_B",
      "message": "此課程可能需等加退選階段才能處理。"
    }
  ]
}
```

| **欄位**       | **必要性** | **說明**                                         |
|----------------|------------|--------------------------------------------------|
| version        | 必填       | schema 版本；App 可依版本做相容處理。            |
| school         | 必填       | 固定為 ntut，未來若支援其他學校可擴充。          |
| semester       | 必填       | 避免不同學期課程 id 混淆。                       |
| studentContext | 建議       | 用於 App 重新檢查階段與限制；不應含帳密。        |
| plans          | 必填       | 依 phase/system 分組，App 不需重新推測送件順序。 |
| warnings       | 建議       | 讓 App 顯示 Web 端已知風險；App 仍需重新驗證。   |

# 10. 規則引擎與回饋分級

| **級別** | **代表意義** | **例子** | **UX 行為** |
|----|----|----|----|
| Error | 目前組合不可送出或高度可能失敗 | 衝堂、超過最高學分、非該階段可選、缺少必要學生身份資訊 | 紅色顯示；阻擋送件；提供修正方法。 |
| Warning | 可以保留規劃，但需注意階段或制度限制 | 跨系班需等加退選、名額未知、新生流程未驗證、先修規則未知 | 黃色顯示；允許保留；送件前再次確認。 |
| Info | 制度提醒或系統資訊 | 博雅志願、英文分班、課程可能由系統匯入 | 藍色提示；不阻擋操作。 |

| **檢查項目** | **MVP 判斷方式** | **進階判斷方式** |
|----|----|----|
| 衝堂 | 以 weekday + periods 判斷重疊。 | 加入開始/結束時間、隔週課、實習課、密集課程與補課例外。 |
| 總學分 | 加總已排課程 credits；新生可先套用 16-25 學分提醒。 | 依學制、系所、延畢、雙主修、研究所規則調整。 |
| 階段資格 | 比對 StudentContext.classCode 與 Course.openClass。 | 加入系所白名單、跨域學程、研究所課程與課程人工覆寫。 |
| 博雅/通識 | 以 category 標示並提醒可能志願選填。 | 建立志願排序與分發結果回寫。 |
| 先修/擋修 | MVP 標示未知，不阻擋。 | 接入課程標準與修課紀錄後再判斷。 |

# 11. API 與資料更新建議

| **API/檔案** | **用途** | **回傳重點** |
|----|----|----|
| GET /api/semesters | 取得可用學期 | semesterId、名稱、資料更新時間。 |
| GET /api/courses?semester=115-1&q= | 課程搜尋 | 分頁、搜尋 facets、course summary。 |
| GET /api/courses/{id} | 課程詳細資料 | 課程時間、教師、限制、raw source。 |
| POST /api/plans/validate | 驗證一份課表草稿 | errors、warnings、phase groups、credits。 |
| POST /api/plans/share | 建立可分享草稿 | shareId / short link；可延後。 |
| ntutbox://planner/import?payload= | 導入 App | base64url 壓縮 payload；避免過長時改 server token。 |

> **資料更新策略**
>
> 選課高峰期資料需比平時更頻繁更新。建議每次資料更新都產生 dataset version，Web payload 也帶上 dataset version；App 送件前若發現版本過舊，提示使用者重新驗證。

# 12. 風險、法務與安全

| **風險** | **影響** | **緩解方式** |
|----|----|----|
| 學校系統流程變動 | 送件失敗或誤判階段 | 將 connector 與 rule engine 模組化；保留 raw response；建立 smoke test。 |
| 高峰期流量造成學校系統壓力 | 可能被封鎖或影響其他學生 | 節流、排隊、手動確認、禁止背景大量 retry。 |
| 帳密與 session 安全 | 高度敏感 | Web 不處理帳密；App 使用安全儲存；避免 log 憑證。 |
| 課程資料錯誤 | 學生排錯課或錯過選課 | 顯示資料更新時間；重要步驟以官方送件結果為準；提供回報錯誤。 |
| 課程評價爭議 | 涉及教師名譽與社群治理 | 延後實作；建立匿名規則、檢舉、審核與使用條款。 |
| 新生系統不可驗證 | 新生可能誤以為可送件 | 明確標示 Beta/未支援正式送件；尋找測試志工後再開。 |

# 13. 建議實作順序

| **順位** | **項目** | **原因** | **完成定義** |
|----|----|----|----|
| 1 | 課程資料 normalize | 所有功能的基礎。 | 能穩定解析課名、課號、時間、教室、教師、學分、開課班級。 |
| 2 | Web 視覺排課與衝堂檢查 | 最快產生使用者價值。 | 加入/移除課程即時更新課表與衝突提示。 |
| 3 | 階段分類：初選 vs 加退選 | 北科特化核心差異。 | 同一份課表能自動切出三個清單。 |
| 4 | App 內手動選課 | 讓 App 先獨立跑通選課 executor。 | 使用者可手動選課並看到逐門結果。 |
| 5 | Web 匯出 plan payload | 準備兩邊整合。 | payload 可被 App 還原，不直接送件。 |
| 6 | App 匯入確認頁 | 降低誤送風險。 | 顯示將送出/不送出/有警告的課程。 |
| 7 | 批次送件與結果回寫 | 完成閉環。 | 每門課顯示結果並同步正式課表。 |
| 8 | 進階決策輔助 | 提升長期留存。 | 替代課、學分規劃、評價、行事曆整合逐步加入。 |

# 14. MVP 驗收清單

| **類別** | **驗收項目** | **通過標準**                                     |
|----------|--------------|--------------------------------------------------|
| 資料     | 課程時間解析 | 常見課程、跨多節課、不同星期課程能正確顯示。     |
| 資料     | 開課班級解析 | 能判斷本班課與非本班課；未知情況不亂判斷。       |
| UX       | 加入課程     | 搜尋結果點擊後 300ms 內更新週課表。              |
| UX       | 衝突提示     | 衝堂時明確指出衝突課程與時間。                   |
| UX       | 階段清單     | 同一份草稿能分成初選可送、加退選、僅規劃。       |
| App      | 手動選課     | 已驗證的兩個系統可完成送件作業。                 |
| 整合     | payload 相容 | Web 產生的 payload 可由 App 解析並顯示完整資訊。 |
| 安全     | 帳密處理     | Web 不接觸學校帳密；App 不記錄敏感資訊。         |
| 營運     | 資料更新時間 | 前端清楚顯示資料來源與最後更新時間。             |

# 15. 參考來源

- 國立臺北科技大學課程系統：https://aps.ntut.edu.tw/course/tw/course.jsp

- 國立臺北科技大學教務處，新生入學＿大學部「選課」頁：https://oaa.ntut.edu.tw/p/412-1008-12962.php?Lang=zh-tw

- MDN Web Docs, Progressive web apps：https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps

- MDN Web Docs, Service Worker API：https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API

- Apple Developer Documentation, Supporting universal links in your app：https://developer.apple.com/documentation/xcode/supporting-universal-links-in-your-app

- Apple Developer Documentation, Defining a custom URL scheme for your app：https://developer.apple.com/documentation/xcode/defining-a-custom-url-scheme-for-your-app

本文為產品與技術規劃文件，不代表台北科技大學官方系統規格。正式選課結果仍應以校方系統為準。

---

# 附錄 A — P1 Web 里程碑切分（Claude 規劃補充，非技術文件原文）

> 技術文件 §4.1 列 8 個 P0 功能、§13 給實作順位。落地時把 **P1（Phase 1 的 Web 端）拆 3 個里程碑**，各自一份 spec → plan → 實作。主軸＝技術文件 §6.1「先讓學生看到課表成形的成功體驗」。
> （2026-06-13 與使用者確認：**先做 M1**；M2/M3 先記錄、之後各走一輪。）

## M1 — 核心排課迴圈（先做深，本次 spec 對象）
**目標**：不登入、不選身分就能跑完整迴圈：搜尋 → 加入 → 看到課表成形 + 衝堂 + 學分。
- 資料載入層：fetch `manifest.json` → 選學期 → 載 `catalog.json` / `periods.json`；前端建搜尋索引（CJK bigram）；先讀本地 `data/v1/`，正式接 `cdn.ntutbox.com/course/v1/`。
- 課程搜尋與篩選（§4.1）：課名/教師/課號/系所/時間/學分；中英文 + 空白 normalize。
- 視覺化週課表 grid（§4.1）：節次 `1,2,3,4,N,5,6,7,8,9,A,B,C,D` 讀 `periods.json`；手機日/週視圖。
- 衝堂檢查（§4.1）：`day × period` 交集；點警告定位到衝突格。
- 學分統計（§4.1）：總學分（排除佔位課 credit=0/0.5）；上限提醒（新生 16–25 為 info）。
- 草稿：localStorage **單份**（多份草稿延到 M3 評估）。
- 命中技術文件 §14 驗收：加入 300ms 內更新、衝突明確、資料更新時間顯示。
- **不含**：身分選擇、階段分類、匯出 payload、PWA/離線（留 M2/M3）。

## M2 — 北科特化分類（差異化核心）
- 身分選擇器：系所/年級/班（讀 `classes.json`，存 localStorage）；§6.1 流程的「選身分」。
- 六類階段分類：`preselection` / `preference_ballot`(博雅·體育·共同英文志願) / `add_drop`(oads) / `program_registration`(微學程/學程/輔系/雙主修) / `planning_only` / `unknown`。用**班級碼**比對、非名稱。
- pool 班級（博雅/體育/英文）/ 佔位課：依 `classes.json` 的 `kind` 與 `is_placeholder` 分支，避免 ~12% 誤判。
- 限制原因 + 規則分級（§10）：Error（阻擋送件）/ Warning（可保留）/ Info（制度提醒）；常駐三清單 + 警告數。

## M3 — 匯出與整合就緒
- 選課計畫 payload 匯出（DESIGN.md §4.6 / `models.py` `PlanPayload`）：按 phase 分組、只帶課號 + 優先序、不含帳密。
- handoff：`ntutbox://planner/import?payload=<base64url>`（Universal Link 優先、URL Scheme fallback；過長改 short token）。
- 分享連結；PWA / Service Worker 離線快取（§架構原則）；（可選）多份草稿 / 每時段備選。
- ICS 匯出標「暫定課表」（技術文件 §4.2 列為 Phase 1 可選）。

## 附錄 A.1 — 技術文件 v0.1 ↔ DESIGN.md 對齊（衝突時以右欄為準）

| 主題 | 技術文件 v0.1 | 以哪邊為準（已鎖定） |
|---|---|---|
| 資料模型 | `Course{courseNo, classNo, openClass?, category}` | `crawler/models.py`（`offering_id`/`course_code`/`classes[]`/`requirement`/`meetings[]`） |
| 開課班級 | `openClass?`（單一字串） | `classes[]` 陣列（一課可多班，§4.6） |
| 階段分類 | preselection / add_drop / freshman / planning_only / unknown | 六類：preselection / preference_ballot / add_drop / program_registration / planning_only / unknown |
| 新生 | freshman 為獨立 phase（Beta） | 折成 `studentContext` 旗標，影響學分上限（16–25 為 info）；不做獨立送件 phase |
| API（§11 `/api/*`） | REST 後端 | 無後端（D5）：靜態 JSON fetch + 前端規則引擎；`validate` 在瀏覽器跑 |
| payload | `courseId` / `system: term_end_preselect` | `offeringId` / `system: cwish`·`oads` / 加 `datasetVersion`（DESIGN.md §4.6） |
| 衝堂精度 | 提到隔週/實習/特殊時段 | 來源無單雙週/半學期 → 只用 `day × period` 交集，不假裝更高精度 |
