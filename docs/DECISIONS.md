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
- **catalog**：任何失敗節點 → 丟棄該學期 catalog 檔與同次人數快照（不做節點拼接）；課數 < HEAD × 0.95 也丟棄（D20 起只限當前學期，其他學期照收＋warning）。
- **standards／mprograms／details**：失敗節點逐一從 HEAD 沿用前一版拼回（HEAD 也沒有的列為缺漏），發 warning 等級告警。
- 丟棄與沿用都列進 `[pipeline] <workflow> 失敗` issue，下一次全部成功自動關閉。

## D17 — runner 釘 `ubuntu-24.04`
所有資料管線 workflow 的 `runs-on` 釘 `ubuntu-24.04`，不用 `ubuntu-latest`。觸發點：GitHub 公告 `ubuntu-latest` 自 2026-10-19 起分批改指向 Ubuntu 26（runner-images#14748），切換期剛好撞上管線 v2 上線與 12/07 的 115-2 選課季；而 publish 依賴映像預裝的 AWS CLI、告警依賴預裝的 `gh`、commit job 依賴預裝的 `git`，映像一換，這些工具的版本或有無可能在程式碼沒動的某一天改變，且分批切換會讓同一支 workflow 前後跑在不同映像上、難以歸因。映像升級排在選課季之後（115-2 選課結束後）另開 PR 統一升，升完手動跑一次 daily／weekly 驗證；屆時一併評估 AWS CLI 改以 pip 安裝並固定版本，降低對預裝工具的依賴。

## D18 — season 自動觸發：排程在 Python、Worker 只觸發；人數改全校一次查（issue #111）
- **觸發不用 GitHub cron**：2026-08-25～09-25 實測每小時排程只觸發 196/744 次、每日排程延遲中位 2.4 小時。改由 Cloudflare Worker Cron 每小時醒來 → GitHub API `workflow_dispatch` `season.yml`。
- **邏輯全在 Python，Worker 只比對與觸發**：derive 產 `data/ops/season-schedule.json`（明確列出每個整點觸發格＋`terms`／`windows`／`reason`），publish 傳到 `course/ops/season-schedule.json`；Worker 只看「現在這個整點在不在 `slots` 裡」。頻率規則、窗口解析、學期歸屬都能在 pytest 驗證，Worker 沒有要測的邏輯。排程檔在 v1 之外、不列進 manifest、不參與過期刪除；範圍＝manifest `calendars` 的學期，不讀系統時間（D11 的確定性）。
- **行事曆只有一個 parser**：選課窗口（預選／新生預選／開學後加退選／期中撤選；歸屬與命名 D19 修訂）由 `term_calendar.py` 推導、寫進週次表 `{term}/calendar.json` 的 `enrollment_windows`（新增欄位，D15 不升 `CALENDAR_SCHEMA_VERSION`），`season_schedule.py` 只展開、不再解析事件——App 與排程看到的是同一份窗口。~~網路選課歸被選的學期~~（D19 改為一律歸發生的學期＋`target_term`）。推不出來的窗口丟棄＋warning，不讓週次表失敗。
- **頻率**（常數在 `season_schedule.py`）：窗口開啟後 24 小時每小時、截止前 24 小時每小時、截止時刻（日間部 17:00、進修部 21:00，取窗口實際截止）補一次、其餘每 3 小時（台北 00／03／06…對齊）；不做深夜暫停。同一整點跨窗口／學期合併成一格。115-1 期中撤選（10/05→11/20、11/21）431 格、115-2 預選（12/07→12/18、12/19）153 格。
- **人數改全校一次查**：`QueryCourse(matric=全校13碼, unit=＊)` 一個請求取代逐系所約 62 個（2026-09-27 實測 115-1：2,778 課、1.86 MB、84.6 秒，課號集合與人／撤數 0 差異；「全校＋所有系所會被擋」早在 2026-06-13 就證實只是前端 JS）。獨立 timeout 180 秒（預設 60 秒會在首個 byte 前逾時）、最多 2 次；失敗（含無表頭、0 課）退回逐系所，來源記進 pipeline-result 的 `enrollment_source`。merge 的人數品質閘門不變（D20 起驟減只對當前學期嚴格）。catalog 仍逐系所（要 unit 歸屬）。
- **告警**（daily 檢查）：`[pipeline] season 窗口學期缺 catalog：<term>`（14 天內有觸發格但該學期沒有 catalog；D19 之後正常不會出現）；`[pipeline] season 未依排程執行`（12 小時內、已過 1 小時寬限的觸發格在 [at, at+1h) 沒有觀測紀錄）。

## D19 — 學期滾動自動化：`active` 納入即將選課的學期；Worker 每週保活 daily／weekly（issue #111）
- **問題**：下學期的預選（校方稱「網路選課」；115-2 在 12/07）在上學期期末舉行，學校 `current-term` 還沒翻；`active` 原本＝`ACTIVE_TERMS` 或 current-term，下學期沒有 catalog → season 必失敗，每學期都得有人記得設 `ACTIVE_TERMS`。
- **`active` 規則改為** current-term ∪ `upcoming_window_terms()`：canonical `{term}/calendar.json` 的 `enrollment_windows` 中，有窗口 `start ≤ now + SELECTION_LEAD_DAYS` 且 `end ≥ now` 的**`target_term`**（`SELECTION_LEAD_DAYS = 30`，env 可覆寫）。所以 115-1 期末時 daily 會同時爬 115-1、115-2，season 監看 115-2。daily 的 calendar 資料集排在 catalog 前，讀到的是當輪剛更新的週次表。窗口來源集中在這一個函式，日後要併入其他來源只改它。
- **`ACTIVE_TERMS` 保留為明確覆寫**：有設就完全照它（不再併 current-term 與窗口），平常留空。
- **影響範圍**：所有 `active` 學期規則的資料集（目前 catalog、mprograms）。2026-09-27 實測：學校對尚未開學的 115-2 已能查到課（全校一次查 4,447 課）、微學程清單 49 個且有開課列，所以提前一個月爬是有資料的；若上游尚未公布，catalog 0 課由 merge 丟棄＋告警（D16 既有行為），不覆寫 canonical。
- **安全網不變**：`[pipeline] season 窗口學期缺 catalog` 仍在 14 天前檢查；正常情況 30 天前就已建出，這個告警出現代表自動納入沒生效（daily 沒跑、行事曆沒窗口、上游 0 課）。
- **保活**：公開 repo 的排程 workflow 在 60 天沒有 repo 活動後會被 GitHub 自動停用（data branch 的 bot commit 是否算活動沒有文件保證）。season Worker 每週一次（台北週一 00:00＝UTC 週日 16:00 的整點）`PUT /repos/poterpan/ntutbox-course/actions/workflows/{daily.yml,weekly.yml}/enable`，期待 204（已啟用時也是 204，冪等）。與 season slot 無關，失敗讓該次 cron 標失敗。用同一把 fine-grained PAT：GitHub 文件「Permissions required for fine-grained personal access tokens」列 enable 端點需要 **Actions: write**，與 dispatch 相同，不必加權限。效果是「被停用最多一週就自動恢復」，不保證重置 GitHub 的 60 天計時。
- **窗口改歸發生的學期＋`target_term`**（修訂 D18）：窗口一律寫進**開始日所在學期**（8～1 月上學期、2～7 月下學期）的 `{term}/calendar.json`，另帶 `target_term`＝被選的學期（預選＝標題的學年度學期，即下學期；其餘＝所在學期）。原因：原本預選歸被選的學期，但 116-1 預選（2027-05-24）要等 116 學年度行事曆（2027-08）才推得出 116-1 的週次表 → 整個窗口被默默丟掉；歸發生的學期後，115-2 的檔就帶著它。season 排程範圍＝所有已推導的檔（所在學期），slot `terms` 取 `target_term`，被選學期有沒有自己的週次表都不影響；`upcoming_window_terms` 也回傳 `target_term`。
- **窗口 kind 改名**（校方「網路選課」其實是預選，易誤會）：`online_selection`→`preselection`（顯示「預選」）、`add_drop`→`post_start_add_drop`（「開學後加退選」；不用裸 `add_drop`——選課階段分類已用它指 oads 系統）、`freshman_preselection`（「新生預選」）、`midterm_withdrawal`（「期中撤選」）不變。season-schedule.json 的 `windows` 用顯示名。`enrollment_windows` 2026-09-27 才加、尚無外部使用者，形狀變更不升 `CALENDAR_SCHEMA_VERSION`（D15）；`TermCalendarFile` 讀舊檔時自動升級（kind 改名、`target_term` 補所在檔學期），下一次 daily 重新推導即改寫。parser_version `calendar/1.2.0`。

## D20 — 課數／人數驟減檢查只對當前學期嚴格
- **問題**：D19 讓 daily 在預選 30 天前（115-2 ≈ 2026-11-07）就爬下學期。學校此時放的是**草案課表**（115-2 實測 4,447 列、無教師、4,176 列沒有時段），正式版約 2.8k（約 −37%）。merge 的「課數 < HEAD × 0.95 → 丟棄」與 publish 閘門（基準＝線上 manifest `count`）會把之後每一次更新都擋掉，該學期永遠停在草案。
- **規則**：驟減比例只對**當前學期**（學校 current-term 偵測結果）嚴格——丟棄／不發佈，行為不變。其他學期（即將選課、過去學期）：0 課／0 列仍丟棄＋告警；驟減 → **照樣採用**，發 warning 等級告警（進 `[pipeline] <workflow> 失敗` issue，人工確認）。人數快照同一套規則；publish 閘門同樣切分。
- **當前學期在 run 內確定**：fetch job 把偵測結果記進 `pipeline-result.json` 的 `current_term`（學期規則沒用到時——明確 `--terms`／`ACTIVE_TERMS`——且有資料集成功，就跑完補偵測一次）；merge 讀它並寫進 merge 報告，commit-publish 從報告取值傳 `publish.py --current-term`。鎖內不再打學校。取不到（偵測失敗、舊 stage、republish、多份報告不一致）→ 全部學期都嚴格（保守，等同原行為）。

## D21 — 本學期 vs 預設學期：期中撤選截止起預設顯示下學期；「回到本學期」按鈕
- **問題**：排課站的預設學期寫死 `115-1`（ui-store、use-term-bootstrap、TermSwitcher 三處），sitemap-courses／hub 跟「manifest 最新學期」。D19 起下學期約在預選 30 天前就進 manifest（草案課表），「最新學期」會在學生還在修本學期、撤選都還沒截止時就把整站推到下學期；寫死的值則每學期要改程式。
- **兩個概念**：
  - **本學期（current）**：台北日期所在的學期——8/1～隔年 1/31 上學期、2/1～7/31 下學期（與 `term_calendar._containing_term` 同一條規則）。
  - **預設學期（default）**：網站預設顯示的學期＝本學期；從本學期的**期中撤選截止**（本學期 calendar.json 中 `midterm_withdrawal` 日／夜間部 `end` 取晚者；115-1＝2026-11-21 17:00、115-2＝2027-05-08 17:00）起改為下學期——那之後本學期已沒有能改的選課動作，學生接著要排下學期（115-2 預選 12/07）。推不出撤選窗口 → 退用下學期預選開始 − 14 天；兩者皆無 → 不提前切換。不看下學期 catalog 是不是草案。
- **資料**：derive 寫 manifest 新增欄位 `term_schedule`（`current`／`default` 兩條 `{term, from}` 時間軸），由 calendar.json 確定性產生、不讀系統時間（D11）；純新增、不升 `SCHEMA_VERSION`（D15）。規則放 Python 是為了跟 season 排程共用同一份窗口、能在 pytest 驗，client 只做「取 `from ≤ now` 的最後一筆」。
- **client 退路**（`apps/web/src/lib/terms/term-schedule.ts` 的 `resolveTerms`，planner／hub build／worker 共用）：預設學期不在 `manifest.terms`（還沒有 catalog）→ 本學期；本學期也不在 → `terms` 最新者。舊 manifest 沒有 `term_schedule` → 預設＝`terms` 最新者（等同 D21 之前）。
- **各處怎麼用**：
  - planner：預設選取＝預設學期；分享連結（`?term=&course=`／`?plan=`）照舊優先。手動切換**不跨次保存**（每次進站回到預設學期）。
  - 「回到本學期（115-1）」按鈕：檢視中的學期 ≠ 本學期時出現在學期選單旁（窄機放 header 下一列），按下切回本學期；本學期沒有 catalog 時不出現。沿用 `AccentButton tone="soft"`、文字用 `--accent-ink` 提高對比。
  - `/sitemap-courses.xml`（worker）：以**請求當下**的預設學期產。
  - `/browse/**` hub：以**部署當下**的預設學期建（build 期）；切換時刻由 D22 的 season-scheduler Worker 觸發重新部署。課程詳情的系所 hub 連結改讀 build 期產出的 `/hub-term.json`（與 hub 同一次載入），不在 client 重算——否則預設學期已切換、重新部署還沒完成（或 hook 失敗）時，連結會指向沒有產生的 hub 頁（404）。

## D22 — web 自動重新部署：資料變動與預設學期切換各自 POST Workers Builds Deploy Hook（Refs #111）
- **問題**：`/browse/**` hub 在 build 期讀 catalog 產靜態 HTML（給不執行 JS 的爬蟲看真實 `<a>`，`apps/web/src/lib/hub/build-catalog.ts`），課程清單凍結在最後一次 code 部署。資料每天更新、預設學期每學期切換，但 web 只在有人 push `main` 時才 build → hub 會悄悄過期。
- **做法**：Cloudflare Workers Builds 的 Deploy Hook（2026-04 起；綁 branch 的唯一 URL，`POST` 無 body、無 Authorization 就 build＋deploy `main`；限 10 builds／分鐘／Worker，已有 build 在 queued／initializing 時重複 POST 回同一個 `build_uuid`、不疊加）。兩個觸發點：
  1. **資料管線**（commit-publish action）：publish 成功（exit 0／3、非 dry-run）後，merge 報告 `applied[]` 中 `name=catalog`、`changed=true` 的學期含**預設學期** → curl hook。預設學期＝`data/v1/manifest.json` 的 `term_schedule.default` 中 `from ≤ now` 最晚的一筆（還沒有 catalog → 本學期 → 最新學期，與 web `resolveTerms` 同語意，D21）；manifest 尚無 `term_schedule`（或沒有已生效的項目）→ **任一學期** catalog 有變就部署——簡單、寧可多 build（hook 去重，多一次的代價只是一次 build），不另寫一套「hub 用哪個學期」的推論。決策在 `infra/web_redeploy.py`（pytest），shell step 只做 curl。人數／課綱變動不觸發（hub 只列目錄）。
  2. **season-scheduler Worker**：每小時讀線上 manifest，這個整點＝某筆 `term_schedule.default[].from` 的生效整點 → POST。預設學期切換不伴隨資料變動（例：115-2 的 catalog 早在 11 月就上線、12 月才成為預設），管線端抓不到，只能靠時間觸發。`from` 不在整點上時取**下一個**整點（截整點會在切換前 build、產出舊學期）；行事曆推導的 `from` 都在整點上，兩者相同。與 season slot、保活無關。
- **secret**：GitHub `WEB_DEPLOY_HOOK_URL`（composite action 讀不到 `secrets`，由各 workflow 以 input 傳入）、Worker `DEPLOY_HOOK_URL`；建議建兩個 hook 各用一邊，外洩時可單獨撤銷。**兩者皆選填**：未設 → 略過（notice／log），不算失敗。
- **失敗不擋資料**：管線端非 2xx（curl 對 5xx／逾時重試一次）→ `::warning` ＋ commit-publish 輸出 `web-redeploy=failed（HTTP …）` → alert job 列進 `[pipeline] <workflow> 失敗` issue；資料 job 不紅燈。Worker 端 manifest 讀取失敗或 hook 失敗 → 該次 cron 標失敗（dashboard 看得到）。URL 本身是憑證，兩邊的 log 都不印。
- **不做**：不改由 worker 動態產 hub（要多一套 runtime 路由與快取，換來的只是省掉幾分鐘 build 延遲）；不在 republish 觸發（沒有 merge 報告，需要時手動 POST 或在 dashboard 重跑）。
