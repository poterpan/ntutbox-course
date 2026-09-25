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

## D11 — 資料管線三層：fetch / derive / publish（2026-09 管線 v2）
舊管線 9 個 workflow 各自爬、各自 `build_v1`、各自上傳，`crawl-detail` 還繞過 derive 直接寫 v1 → 改一個 parser 要記得去哪幾支補跑。
→ 三層、各層只做一件事（spec `superpowers/specs/2026-09-26-data-pipeline-refactor-design.md` §1）：
- **fetch**（`python -m ntut_catalog pipeline`）：打學校／外部來源，**只寫 canonical**（data branch）；不產 v1、不上傳、不在資料內容寫爬取時間。
- **derive**（`python -m ntut_catalog derive --out data`，唯一入口）：canonical → `v1/`＋`reports/`，**全量、確定性**（不連網、不讀系統時間；同一份 canonical 逐位元組相同的 v1）。逐週進度（weekly progress）在這層即時算，行事曆或 parser 改了下次 derive 自動生效。
- **publish**（`infra/publish.py`）：`v1/` → R2，**不重建 v1**；一律全量 MD5 比對只傳差異、manifest 最後推、prefix 內過期刪除（10% 保險）、品質閘門以線上 manifest 的 `count` 為基準。
- 考慮過「由 git diff 推受影響學期、只 publish 那些」：parser／PUA／model 這類只動 derive 的變更沒有 canonical diff，R2 會靜默過期；全量比對只需數秒 → 不採。

## D12 — workflow 依頻率分（daily / weekly / season / maintenance）
一個資料集一支 workflow → 9 支零共用（data branch checkout ×8、R2 env ×8、學期解析 ×6 份 4 種規則），cron 互撞、品質閘門只有一支有效。
→ 依頻率分 4 支＋`test.yml`；資料集與頻率宣告在 `crawler/ntut_catalog/registry.py`，**新增資料集不新增 workflow 檔**。
- **理由**：同頻率的資料集共用一次 runner／checkout／搶鎖／manifest 發佈；只剩兩條 cron（daily、weekly）不互撞；失敗隔離靠步驟與 `pipeline-result.json`（每個資料集獨立 try）而不是靠檔案。
- **代價與對策**：Actions 列表看不出是哪個資料集失敗 → 步驟以資料集命名＋run summary 表＋告警 issue 標資料集；同層慢者拖累他者 → 規則「同層耗時相近，慢的換層」（details 約 53 分鐘，所以在 weekly、不擋 daily 的 catalog 上線）。
- 每支都是「fetch job（不上鎖）→ commit-publish job（`concurrency: data-pipeline`）→ alert job」；「內容有沒有變」一律在鎖內對**最新** data branch 判斷（fetch job 的 checkout 可能已過期）。

## D13 — canonical 不記爬取時間；時間只在 `_meta/fetch-state.json` 與 manifest
舊 canonical 內嵌 `generated_at`、`weekly_progress.parsed_at`、快照列的 `observed_at` → 內容沒變也每週全部重傳（2,727 物件），App 的 ETag／304 全部失效。
→ canonical 只記**內容**。「什麼時候確認過、什麼時候變過」集中在 data branch 的 `_meta/fetch-state.json`（每個 (資料集, 學期) 一格：`checked_at`、`changed_at`、`content_sha256`；無學期維度用 `_global`），由鎖內的 merge 對最新 HEAD 計算；derive 再把它帶進 manifest 各產物項目的 `checked_at`／`changed_at`。
- 人數是例外中的例外：資料本身就是觀測 → 時間在快照**檔名**（`{term}/enrollment/YYYY-MM-DDTHHMM.ndjson`）與 `observations.ndjson`（每次成功爬取追加一行），列內不帶時間；讀取只經 `enrollment_store.latest()`／`history()`。
- 明確接受的代價：上游沒變時，每次 run 仍有一個小 commit（`fetch-state.json` 的 `checked_at`＋`observations.ndjson` 一行）。

## D14 — 時間欄位命名規則
| 名稱 | 意思 |
|---|---|
| `observed_at` | 觀測當下的值（資料本身就是觀測，如人數） |
| `checked_at` | 最後一次成功向來源確認 |
| `changed_at` | 內容最後一次改變 |
| `published_at` | manifest 發佈到 R2 的時間（publish 在上傳前寫入） |

一律 ISO 8601 帶 `+08:00`。其他資料檔不放時間戳。manifest 的 `generated_at` 為相容保留、與 `published_at` 同值（改名會觸發共用 `SCHEMA_VERSION` 升版），待 App 清掉未使用的 `generatedAt` 後再移除。

## D15 — 產物版本規則
- **新增欄位不升版**（Web、App 的解碼器都忽略未知鍵）。
- **移除／改名／改型別 → 升該產物的 `schema_version`**。
- 注意：`SCHEMA_VERSION`（`crawler/models.py`）目前是**全產物共用的單一常數**，升一次所有產物一起跳（拆成 per-artifact 已在 issue #98 評估後不做：App 不以它分支；真需要獨立版本線時照 `CALENDAR_SCHEMA_VERSION` 的模式逐一拆）→ 改名優先用「新增新名＋保留舊名」處理。
- `course/{offeringId}.json` **沒有 `schema_version` 欄位** → 只能做向後相容的變更（例如移除 optional 欄位，2026-09 移除 `generated_at`、`weekly_progress.parsed_at` 即此類）。
- 行事曆 `calendar.json` 走獨立的 `CALENDAR_SCHEMA_VERSION`，App 是**嚴格相等**比對 → 升版會讓舊 App 週次功能停擺，非必要不動。
- App 目前只解碼、不判斷 `schema_version`；真正擋舊 App 的是 manifest 的 `min_app_version`（維持 null）。

## D16 — 節點失敗的處理（部分成功不可默默當成功）
catalog／standards／mprograms／details 都是逐「節點」打上游（一個請求＝一個節點）。單一節點在 client 重試後仍失敗 → fetcher 照舊跳過續跑（不讓一個節點拖垮整輪、請求量不變），但**必須在 `pipeline-result.json` 回報** `failed_nodes`／`node_total`——否則「一個系所 QueryCourse 失敗、該系課程整段消失（只占全校 2–5%，課數閘門抓不到）」會覆寫完整的 canonical 並發佈。
merge（鎖內、對最新 HEAD）的規則：
- 失敗節點 > `node_total` × 5%（repo var `PARTIAL_FAILURE_MAX_RATIO` 可覆寫）→ 整筆 (資料集, 學期) 丟棄、保留 HEAD、告警。
- **catalog**：任何失敗節點 → 丟棄該學期 catalog 檔與同次人數快照（不做節點拼接）；課數 < HEAD × 0.95 也丟棄。
- **standards／mprograms／details**：失敗節點逐一從 HEAD 沿用前一版拼回（HEAD 也沒有的列為缺漏），發 warning 等級告警。
- 丟棄與沿用都列進 `[pipeline] <workflow> 失敗` issue，下一次全部成功自動關閉。

## D17 — runner 釘 `ubuntu-24.04`
所有資料管線 workflow 的 `runs-on` 釘 `ubuntu-24.04`，不用 `ubuntu-latest`。觸發點：GitHub 公告 `ubuntu-latest` 自 2026-10-19 起分批改指向 Ubuntu 26（runner-images#14748），切換期剛好撞上管線 v2 上線與 12/07 的 115-2 選課季；而 publish 依賴映像預裝的 AWS CLI、告警依賴預裝的 `gh`、commit job 依賴預裝的 `git`，映像一換，這些工具的版本或有無可能在程式碼沒動的某一天改變，且分批切換會讓同一支 workflow 前後跑在不同映像上、難以歸因。映像升級排在選課季之後（115-2 選課結束後）另開 PR 統一升，升完手動跑一次 daily／weekly 驗證；屆時一併評估 AWS CLI 改以 pip 安裝並固定版本，降低對預裝工具的依賴。
