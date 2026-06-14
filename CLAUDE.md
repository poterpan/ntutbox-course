# CLAUDE.md — ntutbox-course（北科盒子 排課系統）

> 給 AI session 的導覽。**新 session 沒有先前對話記憶**，這份 + `docs/` 是唯一真相來源。請先讀完本檔，再讀 `docs/DESIGN.md`。

## 這是什麼
北科盒子（NTUT Box）的**課程排課系統**：讓台北科大學生在選課開放前，**公開、免登入**地查課、排課、即時檢查衝堂/學分/選課階段；排好後**匯出一份選課計畫**導入北科盒子 iOS App，由 App 完成正式送件。

- **Web 先行、純規劃**：Web 端**不登入、不送件、不跨域打學校系統**（純前端無法也不應該）。
- **送件在 App**：iOS App（Swift，獨立專案）負責登入與送件；Web ↔ App 只透過「選課計畫 payload」串接。
- 母品牌北科盒子為 **iOS 專屬**、遵循 Apple 美學（Liquid Glass）；本 Web 視覺向其靠攏（可再豐富，但別偏離太多）。

## 現況（2026-06-13）
**P0 爬蟲完成**：`crawler/ntut_catalog/` 已實作（33 tests），110-1～115-1 共 11 學期 32,338 課爬畢，
全過 `models.py` 驗證，產物在 `data/`（canonical NDJSON + v1 JSON artifacts + manifest）。
實作與 live 探測結論（stime 必帶、「全校查詢被擋」其實只是前端 JS 等）見 `docs/superpowers/plans/2026-06-13-crawler-p0.md` 與 `crawler/README.md`。
- **下一步**：P1 Web 排課器（`apps/web/`）或 infra（GitHub Actions cron + R2 發佈）。
- 未爬（P1 需要再做）：課程描述/課綱詳情檔、微學程、課程標準（requirement.category 對映）。

## 路線（技術文件 Phase 0–4）
- **P0：資料 + 爬蟲 PoC**（穩定產出 catalog JSON）← **現在**
- P1：Web 排課器（搜尋/週課表/衝堂/學分/階段分類/草稿/匯出），不登入、不代送
- P2：匯出 plan payload → App 匯入確認頁（Universal Link / URL Scheme）
- P3：App 半自動送件（依 cunum 分組批次）+ 結果回寫 + 錯誤翻譯（reuse NTUT_Tools 的 cwish/oads）
- P4：進階（替代課 / 畢業學分 / 評價 / 行事曆）

## 鎖定的決策（理由見 `docs/DECISIONS.md`）
- **Monorepo**：`apps/web`(Next.js)、`crawler`(Python)、`packages/schema`、`infra`、`docs`。（Cloudflare 綁定用「Root directory」分流，**不用 submodule**。）
- **資料來源**：公開免登入舊版 `aps.ntut.edu.tw/course/tw/`。**不要**用 `/course/mobile/` 換皮版（欄位更少、無 code 連結、官方標「僅供參考」）。
- **管線**：GitHub Actions（Python 爬蟲 cron）→ canonical **NDJSON**（git，commit 歷史＝免費 enrollment 時序）→ 發佈 JSON artifacts 到 **Cloudflare R2**（`cdn.ntutbox.com/course/v1/`）。
- **Web**：Next.js + TS + Tailwind + **shadcn 骨架 + 自訂 Apple/Liquid-Glass 主題**；**無後端、靜態 JSON + 前端 bigram 搜尋 + Service Worker 快取**（PWA、離線）。**不發佈 SQLite**（延後給 iOS/進階版，由同一 canonical 另產）。
- **子網域**：app=`course.ntutbox.com`、靜態資料=`cdn.ntutbox.com/course/v1/`（path 分產品）、`api.ntutbox.com` **預留**給未來動態後端。
- **iOS**：獨立 Swift app，與 Web 只共用「資料合約」（Pydantic `model_json_schema()` → TS 給 web、Codable 給 iOS）。

## 關鍵事實（實作必看；細節在 `docs/DESIGN.md`）
- **課號 vs 課程編碼**：`offering_id`(課號)＝每學期選課代碼、跳動、**= cwish subj**；`course_code`(課程編碼)＝跨學期固定，**同編碼可對多課號(多班)**。主鍵 `(term_key, offering_id)`。
- **節次模型（非直覺）**：不是 1..14，是 `1,2,3,4,N(中午),5,6,7,8,9,A,B,C,D(晚上)`。
- **來源根本沒有的（schema 別假裝有）**：單雙週/半學期、教室↔節次對應、容量上限（catalog 端 `capacity` 恆 null，只 cwish live 有）。`meetings.week_pattern` 預設 weekly。衝堂只用 day×period 交集。
- **班級碼**：== cwish `cunum`（同命名空間）、**逐年重編** → `classes.json` 要**逐學期**產；研究所單一碼不分年級、大學部分「年級+甲乙」。
- **選課階段分類（P0）**：`preselection`(本班直接：本班+同系較低年級選修+授權外班) / `preference_ballot`(志願分發：博雅·體育·共同英文) / `add_drop`(oads：創新創業·國際觀·跨校·三四年級體育·自主學習·跨域專題) / `program_registration`(微學程·學程·輔系·雙主修，非選課系統) / `planning_only` / `unknown`。
- **pool 班級地雷**：博雅/體育/英文掛「pool 班級碼」，學生班級碼永不在其中 → naive 本班/外班會**誤判 ~12%**。`classes.json` 標 `kind: regular|pool|virtual`；佔位課（「請選…」/credit0 無師資）標 `is_placeholder`。
- **送件鐵則（live 實證，§4.6）**：cwish 後端**嚴格驗 (cunum, subj)**；cunum 綁本人授權範圍、subj 必屬該 cunum。→ 扁平志願清單**必依課程所屬班級分組、各帶正確 cunum**，不能全塞同一 cunum。cunum 取自 cwish **live** 本班/外班清單。錯誤→原因對照表見 `docs/DESIGN.md` §4.6。
- **gnehs 參考**：開源「北科課程好朋友」(ISC) 的爬蟲/網站可參考，**不 fork、重寫**。它漏抓授課語言(EMI)、課名被 pangu 加空格、按學制切檔造成重複——別重蹈。

## 解析防呆（爬蟲）
表頭文字定位欄位（**勿寫死欄位索引**——gnehs 因此 language/ta 雙空）；`<a>` 缺失→欄位 null、**勿回退預設值**；html5lib 容錯（來源是未閉合 `<td>` 的 tag soup）；notes 保留原文（會混入「一般教室」這類教室類別字）；credit 用 decimal（有 0.5/0.0 佔位課，加總要排除佔位）；bootstrap 直讀 gnehs 期間：按課號去重 + pangu 空白 normalize、主鍵走課號。

## 目錄
- `docs/DESIGN.md` — 資料架構 / schema / 端點地圖 / 選課規則 / 後端實證（**最重要**）
- `docs/DECISIONS.md` — 技術選型與理由（ADR 式）
- `crawler/` — Python 目錄爬蟲；`models.py` = schema 真相（Pydantic v2）
- `apps/web/` — Next.js PWA 排課器
- `packages/schema/` — Pydantic → TS 型別生成
- `infra/` — Cloudflare（R2/Pages）、GitHub Actions

## 相關專案
- **NTUT_Tools**（**私有** PoC、本 repo 姊妹專案）：台北科大各校務系統的 Python 逆向驗證層。cwish/oads **送件邏輯**（`preselect.py`/`add_drop.py`）已在那驗證，**Phase 3 會參考**。本 repo＝產品；NTUT_Tools＝研究/PoC。
- 使用者技術文件《北科盒子排課系統技術文件 v0.1》：功能分級 / phases / 規則引擎 / payload / MVP 驗收——產品需求來源（請使用者帶入 repo 或詢問）。

## ⚠️ 公開 repo 守則（本 repo 將 public）
**不得放任何個資**：學號、特定學生的班級/cunum/可選課程、帳密、session、`.env`。`docs/` 已去識別化；新增內容也須保持去識別化。

## 慣例
- 規模適配：簡單事直接做；研究/審查類大任務再 fan-out subagent。
- 提交：**只有使用者明確要求才 commit / push**。
- **多 agent 並行 → 各自開 git worktree + 專屬 branch**（2026-06-14 實戰教訓）：本專案常同時有多個 agent（如 crawler 與 web）作業。**切勿共用同一個工作目錄與 `main`**——會互相 `checkout`/`reset` 擠掉對方的 commit（曾把已 commit 的工作 orphan 掉）。做法：① 開工先 `git worktree add ../<repo>-<topic> <branch>` 建獨立工作區（各自 venv）；② 在自己的 topic branch 工作，**不直接推 `main`**（直推會被 auto-mode 擋、也會撞車）→ 走 PR；③ 跨 agent 共用檔（`CLAUDE.md`/`models.py` 等）改動也走 PR，避免覆寫。`main` 視為整合分支、由 PR 匯入。
