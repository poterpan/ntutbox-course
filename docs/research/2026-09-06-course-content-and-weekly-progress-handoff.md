# 課程內容與逐週進度：發布端交接（2026-09-06）

> 收件人：負責 **ntutbox-course** 的實作 agent。撰寫者是北科盒子 iOS App 側的調查員。本文只講**發布端要做什麼**；文中區分「**已核實**」（親自讀過檔案／實測過）與「**建議**」（設計判斷，可推翻但請留紀錄）。

> **2026-09-16 修訂（發布端 agent）**：契約三整節改寫 —— 週次表改由校網 Google Calendar ics 推導，**不再解析官方 PDF**（111～115 十個學期逐筆驗證，證據見 `docs/research/assets/2026-09-16-term-week-table-from-ics/`）。新增契約四「行事曆事件 feed」（poterpan/NTUTBox#181），原契約四「HTTP／CDN 行為」順延為契約五。

> **2026-09-20 修訂（發布端 agent）**：新增契約六「syllabi 的 pass-through 欄位」——`flex_learning` 與 `extra` 從 dict 換成有序的 `label`/`value` 陣列（issue #96），`SCHEMA_VERSION` 2 → 3。原 §7～§9（驗收與契約測試／明確非目標／參考與來源清單）整體順延為 §8～§10。

## 0. 目的與範圍

北科盒子 iOS App 要把本站的課程內容接進主 App。**課程進度的解析放在本站（結構化），App 只讀。** App 端實作不在範圍內（只有 §1 一段交代消費端怎麼用）。六個契約：

1. **`weekly_progress` inline 進每份 `syllabi[]`** —— 逐週主題的結構化衍生欄位，原文 `schedule` 保留。
2. **parser 規則** —— POC parser 搬進發布步驟，加三條新規則，附回歸基準。
3. **`terms/{term}/calendar.json`** —— 目前 404，要新建，而且必須**永續**。（2026-09-16 改寫：**改由 ics 推導、不再解析 PDF**，見 §4。）
4. **行事曆事件 feed** —— 2026-09-16 新增。校網 Google Calendar ics 抓取轉 CDN，取代 App 直打 `calModeApp.do`（poterpan/NTUTBox#181）。
5. **HTTP／CDN 行為** —— ETag／304、Cache-Control、bot 防護與 403/404 語意。

非目標見 §9（Edge API、登入、gold set 阻擋上線、App 端 UI）。

## 1. 背景與消費端需求

App 有兩個入口。**課程詳情頁**：從課表點進一門課，看大綱／評量／教材／本學期進度。**Today 頁**：今日課程下方顯示「本週：主題」。App 端策略是點進課程先秀快取、同時 conditional GET（ETag）；課表同步後與每日首次前景時背景預抓所有已選課程；離線走 last-known-good。App 不登入、不排 SSO 佇列。

對本站的要求只有四條：**每門課一個檔**（已成立）、**ETag 且 `If-None-Match` 回 304**、**體積小到能一次預抓 6～10 門**、**每週重產**（現行 `crawl-details.yml` 週日 05:30 已符合）。

已核實：`crawler/ntut_catalog/artifacts.py:155-164` 把 `canonical/{term}/details.ndjson` 炸成 `v1/terms/{term}/course/{offering_id}.json`；`crawler/models.py:272` 的 `schedule: Optional[str]  # 課程進度` 就是那段自由文字；2026-09-05 實測 `cdn.ntutbox.com/course/v1/terms/115-1/course/360744.json` 回 200，`teacher_code` 已在 payload 內。

## 2. 契約一：`weekly_progress` inline 進每份 `syllabi[]`

**決定：inline，不做 overlay。** 理由三條：原文與解析同檔、同一個 `generated_at`，永遠不會分岔；App 一次請求一個 ETag（Today 要預抓 N 門課，overlay 讓請求數翻倍）；`apps/web` 讀同一份 detail，直接同享。成本是每份 syllabus 約多 1–2 KB，相對已有的 `outline`／`materials` 長文比例不高。

```json
{
  "teacher_code": "23602",
  "schedule": "第1~2週\t機構學概論\n第3-4週\t機構之運動\n…",
  "weekly_progress": {
    "status": "partial",
    "weeks": [
      { "week": 1, "topics": ["機構學概論"], "source_lines": ["第1~2週\t機構學概論"] },
      { "week": 3, "topics": ["機構之運動", "Kinematics of Mechanisms"],
        "source_lines": ["第3-4週\t機構之運動", "Week 3-4: Kinematics of Mechanisms"] }
    ],
    "notes": ["* 第4週後的進度需由各組自行規劃，以下僅作參考。", "第 12 週有 2 個無法判定的候選，已略過"],
    "parser_version": "progress/1.0.0", "parsed_at": "2026-09-06T00:00:00Z", "source_schedule_sha256": "…"
  }
}
```

Pydantic 建議（加在 `crawler/models.py` 的 `Syllabus`（:248-269）之前）：

```python
class WeeklyProgressWeek(BaseModel):
    week: int                       # 1..week_count
    topics: List[str]               # 同一週的語言變體或並列主題；順序＝來源順序，CJK 優先
    source_lines: List[str]         # 原文行，供 UI 顯示來源與人工覆核

class WeeklyProgress(BaseModel):
    status: Literal["resolved", "partial", "unparsed"]
    weeks: List[WeeklyProgressWeek] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    parser_version: str             # 例 "progress/1.0.0"，升版即可離線重產
    parsed_at: str                  # ISO-8601
    source_schedule_sha256: str
```

`Syllabus` 加 `weekly_progress: Optional[WeeklyProgress] = None`。**原文 `schedule` 一律保留，不覆寫。**

**三態定義（2026-09-18 修訂）。** `resolved`：1..`week_count` 每一週都有結果，**彈性學習週除外**——
那幾週教師常不排課或把內容放進彈休區域，1~16 週齊全就算完整（閘門綁 `term.flexible_learning`
的實際日期，不寫死 17/18）。**ambiguous 不再影響 status**，因為多候選現在一律疊加、沒有東西被丟掉。`partial`：至少一週有結果，但存在 missing 或原本 ambiguous 的週次。`unparsed`：沒有任何一週能 resolve，含 `schedule` 為空、TBA、以及 §3 明確拒絕的樣態 —— 這一態仍要寫出來（帶 `parser_version`），App 才能誠實顯示「教師未提供」而不是「載入中」。

**ambiguous 候選怎麼呈現（2026-09-17 改：一律疊加）。** 不設 `candidates` 欄位，**所有候選都寫進
`topics`**，CJK 佔比高的排前面（App 取 `topics[0]` 就是中文）。超過 3 個時在 `notes` 記一行讓 App
自己決定要不要截，但**不丟**。雜訊照收不濾——教師沒換行導致下一週的文字被吃進來這種，我們沒有
可靠方法判斷哪裡該截，硬截會砍到真內容。

原案是「恰有 2 個候選＋雙語配對才合併，其餘整週丟棄」。三個門檻互相絆倒，實測踩到：
361410 第 9 週中文「期中考（Mid-term Exam）」CJK = 0.18 < 0.3；361535 第 15 週英文
「/16/17/18 Final Project」拉丁 = 0.57 < 0.6（差 0.03）；361535 第 12 週教師真的寫了兩次 → 3 個候選。
依據：全量 751 個 ambiguous cell 中 **97.1% 恰好 2 個候選**，一行式「主題A／主題B」夠用。
原本「丟給 client 會讓每個 consumer 各自發明取捨」的理由已不成立——consumer 只有本站的 App。

**多 syllabus：每份各自一份 `weekly_progress`，不合併、不投票、不取第一份。** 理由：115-1 有 **112 個開課實例**的不同教師寫了互相衝突的進度，挑哪一位是 consumer 的事。衍生資料的身分鍵是 `(term_key, offering_id, teacher_code, source_schedule_sha256)`；`source_schedule_sha256` 或 `parser_version` 一變就必須重產。

## 3. 契約二：parser 規則

POC 在 `/Users/poterpan/Documents/Coding/NTUT/ntut-course-progress-poc`（320 行、無第三方依賴）。建議搬成 `crawler/ntut_catalog/parse_progress.py`，由 `crawler/ntut_catalog/detail.py:20` 的 `crawl_detail` 在建完 `Syllabus` 後呼叫；**另加一支離線子命令**（照 `cli.py:108-110` 的 `recategorize`／`rematric` 先例），讓 `parser_version` 升版時不必重爬學校系統就能重產。

### POC 已記錄的 6 條陷阱（逐條抄過去，`docs/POC_FINDINGS.md`）

1. `第19週` 若 regex 沒有數字邊界，會被錯讀成第 9 週。
2. `第4週後的進度需自行規劃` 是備註，不是第 4 週的 topic → 進 `notes`。
3. 有老師用 `一週／二週` 表示「這單元要花一到兩週」，不是第 1／2 週。**中文數字沒有「第」時保守拒絕。**
4. `Week 2: class time may move to week 3 …` 後半的 week 是敘述。**每行只接受第一個 marker**，非連續週必須靠 list marker（`第17、18週`）。
5. 中英雙語各寫一遍會產生同週不同語言的候選。**沒有可靠語言配對時不得硬合併字串**（見下方規則 a）。
6. `第4週～第8週` 兩端都有「週」，range regex 必須整段吃掉，否則會拆成兩個單週。

### 三條新規則（**建議**；閾值需以 fixtures 校準）

**(a) 候選排序（原「雙語配對」，2026-09-17 降級）。** 從閘門改成**排序鍵**：同一週的所有候選
全部疊加，CJK 佔比高的排前面。不再有「恰有 2 個／CJK ≥ 0.3／Latin ≥ 0.6」那三道門檻。

**(b) 編號＋日期表。** 逐行以 tab／連續空白切欄。若同時滿足：首欄可解析為整數且序列**從 1 開始、單調 +1、無缺口**；另有一欄可解析為 `M/D` 或 `M月D日`；**所有相鄰列的日期差恰好 7 天**（不是平均 7 天，是每一對都是 7）→ **首欄即週次，自動接受**。**拒絕**：任一相鄰對不是 7 天（調課／放假會出現 14 天，這時不要猜）、序列不從 1 開始或有缺口、列數 < 12（建議值）。年份補齊：以該學期 `weeks[0].start` 的年份起算，月份回捲（12 → 1）時 +1 年。依據：使用者實測第 4 門課 18 列、間隔全為 7 —— **首欄 1..18 與「每列差 7 天」互相證明**，資料自己驗證自己。

**(c) 純日期清單。** 行內只有日期 marker、沒有週次 marker 時，用該學期 `calendar.json` 的 `weeks[]` 把日期映射到週次。**需要契約三先就位。**
（實作：規則 (b)(c) 都要吃 `weeks[]`；該學期沒有 `calendar.json` 時**這兩條自動停用**、marker 路徑照常運作，
report 的 `term_weeks_available` 會標 `false`。規則 (b) 需要它是為了補年份——月份回捲 12→1 時要 +1 年。） **拒絕**：映射結果有重複週次，或任一日期落在學期外 → **整份拒絕**（日期表格式通常一致，局部失敗代表判讀方向錯了，不做部分接受）。

### 兩條後補規則（**2026-09-16 加，依涵蓋率盤點的結果**）

盤點 115-1 全量後發現，解不出來的 983 筆裡有兩塊不是「教師沒寫」而是我們漏抓：

**(d) 行事曆錨點編號清單。** 原本一律拒絕沒有日期佐證的純編號清單（「很可能是章節」）。
行事曆提供了一個原本沒有的獨立證人：若一張 12～18 列、首欄 1..N 連續的清單，
**第 N 列剛好寫「期中考」而行事曆說期中考就在第 N 週** → 首欄即週次。
與規則 (b)「首欄與每列差 7 天互相證明」同一個雙證人精神。

- **只用期中考，不用期末考。** 這是量出來的：115-1 全量掃過，期中考落在行事曆對應週的
  偏移分布在 0 有一個銳利的峰（132 筆）、尾巴很小；**期末考完全不可靠** —— 峰值在
  +1（82 筆）與 +3（53 筆）、剛好只有 16 筆，因為考期 12/18–12/24 橫跨第 15、16 週，
  而且很多教師把「期末」寫在最後一列（第 18 列，彈性學習週）。
- **要求剛好對上，不給 ±1 容差。** 容差一放佐證就垮。寫了期中考但不在對應那一列 →
  **整份拒絕**（首欄很可能是「第幾次上課」）。實測有一份把 `Mid Term Exam` 寫在第 7 列，
  就是這條擋下來的。
- 精度佐證：收進來的 125 筆中，有 31 筆的列內自帶日期可獨立交叉驗證，**31/31 全數吻合**。

**(e) 跨行 marker。** 週次標記獨占一行、主題在下一行：

```
第1週
09/10 課程內容簡介 Course Overview
第2週
09/17 晶體結構與矽半導體物理特性
```

來源是表格的儲存格換行變成文字換行，**週次其實明確寫著** —— 這是修 bug，不是放寬判準。
只在下一行本身不含任何週次 marker 時才併（否則 `第1週 ⏎ 第2週 導論` 會誤併），
併進來的主題若以日期開頭就把日期剝掉。

### 規則之間怎麼仲裁（2026-09-18）

**取解出最多週的那個結果，不是先命中的那個。** marker 路徑與規則 (b)(c)(d) 各有自己的證據
門檻，多條同時成立時它們都可信，沒有理由不挑最完整的。實測踩到：

- **362282** 主題文字寫著「請明確**第二週**實驗順序」，那個「第二週」被當成 marker，
  marker 路徑抓到 1 週就擋掉 1~16 齊全的編號表
- **362890** 規則 (c) 先命中只回 15 週（13~15 那三列沒寫日期），(d) 回得了 18 週
- **364517** 規則 (b) 先命中，但日期與主題同格時（`6\t10/15讓演算法…`）主題被吃成空字串，
  18 列只剩 10 週有效

由構造保證不會變差——舊結果必定是新結果的候選之一。順帶解掉「假 marker」：它只會產出
1 週，必然輸給完整的編號列，不需要另外做很難做對的「偵測假 marker」。

### marker 與首欄的變體（依實機盤點補的）

| 形態 | 實例 |
|---|---|
| 英文 list `Week 15/16/17/18` | 361535（中文早就支援、英文沒有，這個不對稱是該筆漏週的根因） |
| 序數 `1st week` / `10th week` | 360934 |
| `WK#01` / `WK-1` | 361223 / 366869 |
| `Week 1_Syllabus` | 364628（底線算單字字元，結尾 `\b` 不成立 → 改用 `(?!\d)`） |
| `週 01.`（週字在數字之前） | 361439 |
| 全形 `Ｗeek` | 362327（逐字 1:1 轉半形，offset 不變、topic 仍從原文切） |
| 點號 list `第1.2.3.4週` | 363052 |
| 首欄中文數字 `週次 / 一 / 二` | 360924、361168、361488 |
| 首欄合併列 `3-4. 機器學習` | 360754（展開成多列共用主題） |
| 首欄冒號 `1: 課程介紹` | 361781 |
| 首欄前導零＋括號日期 `001(09/10)` | 361761 |

### 不產逐週進度的課（2026-09-17）

**體育**（115-1 共 244 門，課名一律「體育」）。進度欄常是「一堂課塞很多活動」，沒有正確答案
可抽、抽出來也沒意義，且通常不照表操課。用 `weekly_progress: null`（我們沒產），
**不是 `unparsed`**（教師未提供）——後者會讓 App 顯示不實陳述。清單在
`PROGRESS_EXCLUDED_COURSE_NAMES`，清空即可全部恢復，不必重爬。

### 明確拒絕（不論看起來多像）

- **沒有日期欄佐證的純編號清單。** 使用者實測第 3 門是 `1.`…`14.`，14 項對不上 18 週，很可能是章節。**建議連「項數恰等於 `week_count`」也一併拒絕** —— 那只是巧合，只有一個證據不足以判定。取捨：會少救一些課；但誤把章節當週次是使用者看得見的錯誤，比空白嚴重得多。UI 顯示原文清單即可。
- 空值、或短到不可能有內容（< 4 字）→ `unparsed`。**不得臆造教師沒寫的內容。**
  ⚠️ **2026-09-18 移除「TBA 類字串全文掃描」**：那會把整份完整的進度表丟掉。實測 366876／
  366838／366828 的 18 週全解得出來，卻因文末一句「教師可視情況做出調整」整份被判 unparsed；
  364705 是第 5 週寫了「專題演講 (待定)」。那些是教師的免責註記。而且早退本來就多餘——真的
  只寫 TBA 的話，所有規則都找不到東西，自然會走到 `unparsed`。
- **時長不是週次**（2026-09-18 新增）。`9週迎新／1週圖書館／2週工程倫理／6週專題`（9+1+2+6=18）
  是依序分配的時長，輸出「第 9 週＝迎新活動」是錯的。三個條件缺一不可：所有 marker 都沒有「第」、
  原始行序不是從 1 遞增、起始週加總落在合法授課週數。條件一是關鍵——`第2週 星期二`／`第2週 星期三`
  這種同一週分兩天的寫法加總也會湊到 18，那是巧合。命中就整份拒絕，**不臆造區間**。

### 回歸基準（CI 必跑）

| 項目 | 門檻 | 第一版 | 現況（2026-09-18） |
|---|---|---|---|
| `resolved_lookup_cell_rate` | ≥ **0.4725** | 0.5004 | **0.7053** |
| `schedule_parse_coverage` | ≥ **0.5697** | 0.5742 | **0.7789** |
| `observed_115-1_range_cases.json` 的 7 個真實樣本 | **全數逐段逐字通過** | 通過 | 通過 |
| `gold_cases.json` 的 19 筆 | **逐段逐字通過** | 通過 | 通過 |
| POC 全量數字（1255 segments／18735 resolved） | 不得低於 | 相同 | 1255／19063 |

⚠️ **POC 數字從「逐項相同」變成「不得低於」**：規則 (e) 刻意讓 marker 路徑變強，等號不再成立。
逐字保真的保證改由 gold_cases（19 筆）與 observed 樣本（7 筆）承擔，那兩份仍是逐段逐字相等。

**開課實例層級的實際涵蓋率**（115-1，2026-09-14 資料，2,767 份已發佈的 course 檔）：

| | 最初 | 現況（2026-09-18） |
|---|---:|---:|
| 能顯示至少一週 | 1,192（43.7%） | **1,503（54.3%）** |
| 能排滿 1–16 週 | 940（34.5%） | **1,320（47.7%）** |
| 隨機（課, 週）可顯示 | 38.2% | **49.0%** |
| 實際產物三態 | — | resolved 1,461／partial 223／unparsed 524／null 116（體育） |

仍為 0 週的 1,273 門中，**789 門根本沒有 syllabus**（占全部的 29.0%）——那是天花板。
其餘多數是「每週meeting」「不定時進度討論」這類**教師本來就沒寫逐週計畫**的專題／實習課，
不得臆造。

**回歸語料已進 repo**：`crawler/tests/fixtures/weekly_progress/schedules-115-1-c3cd485c.json.gz`
（2,203 筆 schedule 原文，gzip 528 KB）。原本只存在於 `data` branch 的 11 MB `details.ndjson`，
CI runner 取不到就等於門檻跑不了。⚠️ **語料裡的 email 一律遮成 `<email-redacted>`**（8 個個人
gmail、2 個校內信箱），實測遮罩前後三個數字完全相同，不影響基準——見下方「一個順帶發現」。

基準取自 `snapshots/115-1-poc-report.json`（對 `origin/data` commit `c3cd485c` 的 `115-1/details.ndjson` 全量跑）。7 個樣本涵蓋完整 range 表（`360752`）、備註陷阱（`360986`）、list marker（`361237` 的 `第17、18周`）與校方異常標點（`360826` 的 `第13-15: 週`）。新規則只能把數字往上推；往下就是回歸。

**每次發布把三態統計寫進 report**：`canonical/reports/{term}/weekly-progress.json`
（resolved／partial／unparsed 課數與 lookup cell 比例）。**不是原案的 `data/reports/`** ——
`data` branch 只掛在 `canonical` 這一層，寫在外面等於永遠進不了版控、長期精度追蹤就沒了。**gold set 不阻擋上線** —— POC 建議的「≥200 筆分層 gold set、precision ≥98%」是**宣稱 precision** 的門檻，不是上線門檻；上線靠三態誠實揭露 ＋ `parser_version` 逐步提升。

## 4. 契約三：`terms/{term}/calendar.json`（**2026-09-16 改寫：改由 ics 推導，不再解析 PDF**）

> **本節在 2026-09-16 被推翻重寫。** 原案是「自動發現最新行事曆 PDF → `pdftotext -layout` 解析」。
> 實測顯示週次表可以只用校網 Google Calendar ics（見契約四）裡的兩個具名事件推導出來，
> 111～115 五個學年度、10 個學期逐筆與官方 PDF 週次表相同 —— 所以 PDF 的**執行期依賴整個拿掉**。
> 證據與可重跑腳本：`docs/research/assets/2026-09-16-term-week-table-from-ics/`。

使用者原本的驗收標準沒有變，只是換了更好的解法：

> 「我希望那邊能夠有辦法**永續解析最新 PDF**，不然只要我一停止維護，這個功能就會失效。」

拿掉 PDF 之後這條反而更穩：不再需要抓 `oaa.ntut.edu.tw` 列表頁（目錄 id `2878` 是 CMS 內部值、會變）、
不需要解 PDF 版型、CI 不需要裝 poppler。ics 的具名事件是結構化的，版型不會變。

### 推導規則（兩條，已對 10 個學期驗證）

- **第 1 週** = 開學日所在的那一週，**週日起算**。PDF 把再前一週標「準備」、不給編號，所以 `preparation` = 第 1 週的前一週（日～六），推導即可。
- **末週** = 假期開始日（`寒假開始` / `暑假開始`）前一個週六所在的那一週。

`week_count` 是**推導出來的，不是寫死 18**。兩條規則跑完，111～115 十個學期都得到 18；哪一年不是 18，就是不變量①失敗、停下來讓人看。

### 具名日期怎麼取

| 欄位 | ics `SUMMARY` 比對 | 備註 |
|---|---|---|
| `administrative_start` | `學年度第N學期開始` | 實際固定為 8/1 與 2/1 |
| `instruction_start` | 含「開學」 | **需要 tie-break**，見下 |
| `midterm` | `期中考試` | **原案說只有 PDF 有、快照漏收 —— 錯了，ics 有**，且與 PDF 值相同 |
| `final_exam` | `期末考試` | |
| `flexible_learning` | `彈性學習週` | **115 學年度才出現**，舊學期沒有 → 必須 optional |
| `break_start` | `寒假開始` / `暑假開始` | |
| `preparation` | 無對應事件 | 推導（第 1 週前一週），provenance 標 `derived` |

**兩條 tie-break（實作時依實測補的，套用順序如下）**：

1. **校級優先於學制專屬**：候選中若有不含「進修部」「日間部」的，只留那些。
   實測 111-2 的「期末考試」命中兩筆——校級那筆，以及「進修部期末考試(6/17 補行上班，停課一次)」。
   `calendar.json` 描述的是全校學期行事曆，學制專屬的是例外附註。
2. **「開學」再取正式那筆**：措辭逐年不同（115-1「開學暨註冊截止日、開學典禮」、
   115-2「開學正式上課、註冊截止日」），優先取含「正式上課」或「註冊」的。

111～115 每個學期、每個欄位都收斂到唯一一筆。收斂不到 → **不變量⑧失敗，不得靜默猜**。
`期中考試` / `期末考試` 這兩個 pattern 夠窄，不會誤中「期中撤選」「英文期中會考」。

全天事件在 ics 是 end-exclusive，取 inclusive 迄日時一律 `DTEND − 1 天`（處理方式與契約四同一套，不要各寫一份）。

### 輸出形狀

```json
{
  "schema_version": 1, "timezone": "Asia/Taipei",
  "week_starts_on": "sunday", "range_end_semantics": "inclusive",
  "source": { "type": "google_calendar_ics",
              "url": "https://calendar.google.com/calendar/ical/docfuhim9b22fqvp2tk842ak3c%40group.calendar.google.com/public/basic.ics",
              "content_sha256": "…", "parsed_at": "2026-09-16T…Z", "parser_version": "calendar/1.0.0",
              "derived_fields": ["weeks", "preparation"] },
  "terms": {
    "115-1": {
      "administrative_start": "2026-08-01",
      "preparation": { "start": "2026-08-30", "end": "2026-09-05" },
      "instruction_start": "2026-09-07",
      "weeks": [ { "number": 1, "start": "2026-09-06", "end": "2026-09-12" }, "… 共 18 筆" ],
      "midterm": { "start": "2026-11-02", "end": "2026-11-06" },
      "final_exam": { "start": "2026-12-18", "end": "2026-12-24" },
      "flexible_learning": { "start": "2026-12-28", "end": "2027-01-08" },
      "break_start": "2027-01-11"
    }
  }
}
```

**`schema_version` 刻意不跟 repo 的全域 `SCHEMA_VERSION` 綁**（`crawler/models.py:27`，目前 = 3）。
全域版本是任何一個 model 改動就 bump 的；綁上去等於**課程 schema 的不相干改版會讓 App 整份拒收行事曆**。
calendar 與 events 走自己的版本號、從 1 開始 —— 所以 #168 的 `supportedSchemaVersion = 1` 不用改。
這是刻意偏離 repo 慣例，理由記在 `docs/DECISIONS.md`。

`source.content_sha256` 是**正規化後**事件集合的雜湊，不是 ics 檔案的 md5 —— VEVENT 排列順序不穩，檔案雜湊每次都不同。

欄位名沿用 `NTUT_Tools/docs/research/snapshots/term-calendar-115.json` 的 snake_case，
逐學期檔仍保留單鍵的 `terms` map，讓 App 現行 decoder（`NTUTBox/Services/TermCalendarProvider.swift:119-163`）**一行都不用改**。
對照 `NTUTBox/Models/AcademicTermCalendar.swift:22-64`：

| App 屬性 | 來源 |
|---|---|
| `termKey` | `terms` 的 key |
| `classesStart` / `classesEnd` / `weekCount` | 由 `weeks` 衍生（首週 start／末週 end／筆數），**不入 JSON** |
| `weeks[].number` / `.start` / `.end` | 同名直取（App 用 `number`，**不要改叫 `index`**） |
| `instructionStart` / `midterm` / `finalExam` / `flexibleLearning` / `breakStart` | `instruction_start` / `midterm` / `final_exam` / `flexible_learning` / `break_start` |

### 產出範圍（2026-09-19 修訂）

**新學年度尚未匯入不是錯誤。** 教務處分批匯入行事曆、沒有固定節奏（112 學年度下學期拖到
2024-02），所以每年 8 月之後有一段期間 `default_terms()` 要的學期在 ics 裡是空的。那種學期
**安靜跳過**（`TermNotPublishedYet`）；全部都空就回空字典、保留既有週次表不動。
**不可以讓它非零退出**——`crawl-calendar` 會連事件 feed 一起停更（實測 2027-08-01 必然觸發）。

「有事件但湊不出合法週次表」仍然是硬錯、仍然全有全無——那代表規則或來源壞了。

**上傳不吃 `--terms`**：週次表只需要行事曆、不需要課程目錄，下學期的往往早於課程目錄就能產
（#168 要的正是提前拿到）。綁 `--terms` 會讓它停在本機永遠不上線。

**只產當前學年度的兩個學期**（由今天推算，現況 115-1、115-2），舊學年度不回填。
App 只用得到當前學期與下學期；而舊學年度沒有 PDF 可對，且實測會踩到真實例外——
**108-2（COVID 那年）延長學期，期末考 2020-06-29~07-05 落在推導出的學期範圍外，不變量⑤ 擋下**。
回填只是把這類例外變成維運負擔。

**全有或全無**：兩個學期是同一份來源、同一套規則推出來的，其中一個不對代表規則或來源有問題，
這時把另一個照發只是把錯誤藏起來 → 一起不寫。

### 不變量（全過才發布）

① 推導出來的 `week_count` **等於 18**。不等於 18 → 失敗並要求人工確認，**不得自動放行**。（推導與門檻是兩件事：`week_count` 由規則算出，這條只負責在算出非 18 時把人叫來。）
② 每週 `end − start == 6 天`，相鄰週 `weeks[i+1].start − weeks[i].end == 1 天`。
③ 每週 `start` 的 weekday 是**週日**（Asia/Taipei）—— 這條專抓「開學日 + 7×(N−1)」那個經典錯誤。
④ `instruction_start` 落在第 1 週的 `[start, end]` 內。
⑤ `final_exam` 完全落在 `weeks[0].start … weeks[-1].end` 內。
⑥ `break_start` > `weeks[-1].end`。
⑦ 同學年兩學期不重疊（`{Y}-1` 末週 end < `{Y}-2` 首週 start）。
⑧ **關鍵字唯一性**：`開學`（tie-break 後）／`期中考試`／`期末考試`／`寒假開始|暑假開始` 在該學期區間內**各自恰好命中 1 筆**。0 筆或 ≥2 筆 → 失敗。**這條取代了原本「相信 PDF 解對了」的位置，是 ics-only 之後的主要防線。**
⑨ **必填非 null**：`instruction_start`、`break_start`、`midterm`、`final_exam`。App 要靠這四個欄位取代中文關鍵字耦合（見下），缺一個就等於那邊要退回猜字串。
⑩ **回歸**：111～115 十個學期的推導結果必須與 `pdf-week-tables-111-115.json` **逐筆相同**。這份是從校方公告 PDF 抽出來的答案，凍成離線 fixture，以後不需要再碰 PDF。（取代原案只對 115 一個學年度回歸的不變量⑧。）

**⑩ 必須在「發佈時」跑，不能只放在 pytest。** 理由見 §8：**本 repo 目前沒有任何跑測試的 CI**。把這條放進 `quality_gate` 一起跑，等於每次發佈都拿 10 份校方公告答案重驗一次解析規則 —— 成本是把那份 fixture 一起帶進 `crawler/`（8.9 KB，離線、無外部依賴），換到的是「ics 改措辭時當天就被擋下」。ics-only 的安全論證整個押在這條上，不能讓它取決於有沒有人記得跑 pytest。

任一不過 → **保留上一版、CI 紅燈、log 印出是哪一條不變量、哪個學期**。

實作上這兩件事是分開達成的（**不阻斷課程目錄的發布，但必須讓人看見**）：

- 推導失敗時 `crawl-calendar` 直接拋錯、**不寫出任何產物**，所以 R2 上的舊 `calendar.json` 原封不動
  （與 `infra/publish.py:45-51` `quality_gate` 同樣是 pre-flight 語意：擋在上傳之前，不是事後 rollback）。
- workflow 對該步驟是 `continue-on-error: true`，讓當日的 catalog/enrollment 照常 commit 與發布；
  **但在 publish 之後有一步專門把它變成紅燈**（`crawl.yml` 的 `Fail if calendar step failed`）。
  少了這步，「校方改了措辭、週次表停在上一版」會靜默過去——那正是換源要消滅的失效模式。

### 消滅 App 端的中文關鍵字耦合

#181 指出 App 有三處靠事件標題的中文關鍵字反推語意，措辭一改就靜默失效。
契約三的結構化欄位（加上不變量⑨保證非 null）讓那三處可以全部改成讀欄位：

| App 現況 | 改讀 |
|---|---|
| `NTUTBox/Services/VacationQuietLogic.swift:70,112` 比對「寒假開始／暑假開始」 | `break_start` |
| `NTUTBox/ViewModels/CalendarViewModel.swift:641,651` `detectSemesterRange()` 用「開學」+「寒假／暑假開始」 | `instruction_start` + `break_start` |
| `NTUTBox/Services/TermCalendarCrossCheck.swift:42-70` 拿「開學」比對 `instructionStart` | 直接讀 `instruction_start`；**這支可以整個刪掉**，它要 cross-check 的東西現在就是資料本身 |

關鍵字比對沒有從世界上消失，它搬到了發布端**一處**、有 10 個學期的歷史語料釘住、而且壞掉時 CI 會紅燈。

### 發布端接線（已核實）

照 **mprograms** 的形狀做（唯一「逐學期＋進 manifest」的既有樣板）：
`canonical/{term}/calendar.json` → `artifacts.py` 的 `build_term_calendars_v1` →
`artifacts.py` 的 manifest 檔名清單加 `calendar` → `infra/publish.py` 的逐學期白名單加 `calendar.json`。

⚠️ **一個與 mprograms 不同的地方**：週次表**不能**跟著那個「逐學期 catalog 迴圈」跑。
那個迴圈要求 `canonical/{term}/catalog.ndjson` 存在，但下學期的週次表往往早於課程目錄就能產
（#168 要的正是提前拿到）。所以 v1 的週次表走自己的一輪掃描，不綁課程目錄是否已爬。
連帶結果：只有週次表、還沒有 catalog 的學期**不會進 manifest**（`ManifestTerm.catalog` 是必填），
檔案照常發佈——這與 `names.json`／`standards/` 的既有先例一致。
**三份名單漏改任何一份都是靜默不發佈。**
`ManifestTerm` 已加 optional `calendar: ManifestEntry`，沿用既有 url／sha256／size 契約。
⚠️ **該 entry 的 `schema_version` 走獨立的 `CALENDAR_SCHEMA_VERSION`（1），不是全域的 2**——
不區分的話 manifest 會說 2 而檔案本身寫 1，App decoder 對版本不符是整份拒收、且是靜默失效。
逐課 detail **不要**進 manifest（2,461 個條目會把短快取的 manifest 撐爆）。

## 5. 契約四：行事曆事件 feed（**2026-09-16 新增**）

> 需求來源：**poterpan/NTUTBox#181**。App 現在直接打學校的 `calModeApp.do`，那個 API 的資料慣例會無預警改變 ——
> 2026 年起單日全天事件從 end-exclusive 變成 `calStart == calEnd`，造成 58 筆事件整批從 App 消失、
> 沒有任何錯誤訊息（#180，已修）。改用校網自己提供的 Google Calendar，由本站抓取轉 CDN。

### 為什麼由發布端轉，不讓 App 直抓（已實測，2026-09-14）

| 標頭 | 值 |
|---|---|
| `ETag` | **沒有** |
| `Last-Modified` | **沒有** |
| `Access-Control-Allow-Origin` | **沒有**（帶 `Origin` 重測仍無） |
| `Cache-Control` | `no-cache, no-store, max-age=0, must-revalidate` |

送 `If-Modified-Since` → 回 **200 + 完整 201,696 bytes**，不會 304。**條件式 GET 無效，每次都是全量。**
App 直抓等於每次啟動拉 34.5 KB（gzip 後）且無法快取；瀏覽器端更是直接被 CORS 擋死。
轉 CDN 之後這些全部補上，而且與契約三共用同一次抓取。

### 覆蓋率：換源不會漏資料（已實測）

區間 2026-08-01 ~ 2027-07-31 逐筆比對（標題／起日／迄日三元組）：學校 API 具名事件 97 筆、
Google ics 97 筆，**學校有 Google 沒有：0 ｜ Google 有學校沒有：0 ｜ 日期不一致：0**。
學校 API 另有 105 筆 `holiday_system` 標記，實測 522 個標記日**落在週一～週五的是 0 天** —— 它只是週六日，
不是國定假日（真正的國定假日兩邊都靠具名事件表達，已含在 0 差異內）。**換源唯一失去的是純週末標記，App 端用 `weekday` 自算。**

### 來源與資料形狀（已實測）

`https://calendar.google.com/calendar/ical/docfuhim9b22fqvp2tk842ak3c%40group.calendar.google.com/public/basic.ics`

`basic.ics` 與 `full.ics` **內容完全相同**（同 bytes、同 UID 集合、含 DESCRIPTION/LOCATION 的簽章 md5 亦同），不需要選。
661 筆 VEVENT，涵蓋 2019-05-27 → 2027-07-03。全天 538 筆、有時刻 123 筆、**缺 `DTEND` 4 筆**（都在 2019–2020，parser 要能容忍）。
`RRULE` / `RECURRENCE-ID` / `EXDATE` 各 0 筆，不必處理重複展開。無 `VTIMEZONE`、無 `TZID`；有時刻的事件一律 UTC `Z` 後綴，
日曆層只宣告 `X-WR-TIMEZONE:Asia/Taipei`。`UID`、`SEQUENCE`、`LAST-MODIFIED` 661 筆全有。

**全天事件一律 end-exclusive，無例外**（單日 `DTEND − DTSTART == 1 天` 有 393 筆，`== 0 天` 的 **0 筆**）——
學校 API 那個壞形態在這裡不存在，這是換源最具體的理由。

### 輸出形狀

端點 `cdn.ntutbox.com/course/v1/calendar/events.json`，**全量單檔**（gzip 後約 25–35 KB）。

```json
{
  "schema_version": 1, "timezone": "Asia/Taipei", "range_end_semantics": "inclusive",
  "source": { "type": "google_calendar_ics", "url": "…basic.ics",
              "content_sha256": "…", "fetched_at": "2026-09-16T…Z", "parser_version": "calendar-events/1.0.0" },
  "horizon": { "max_start": "2027-07-03", "covers_through_academic_year": "115" },
  "events": [
    { "uid": "…@google.com", "summary": "寒假開始、寒宿開始",
      "all_day": true, "start_date": "2027-01-11", "end_date": "2027-01-11",
      "description": null, "location": null, "sequence": 0, "last_modified": "2026-07-15T…Z" },
    { "uid": "CSVConvert…", "summary": "…",
      "all_day": false, "start_at": "2026-11-02T09:00:00+08:00", "end_at": "2026-11-02T12:00:00+08:00",
      "description": null, "location": null, "sequence": 0, "last_modified": "…" }
  ]
}
```

**日期語意（#180 的教訓，不要再踩）**：

- 全天事件 → `all_day: true` + `start_date` / `end_date`，**inclusive 本地日期**。ics 的 end-exclusive 一律 `DTEND − 1 天`。
- 有時刻事件 → `all_day: false` + `start_at` / `end_at`，ISO-8601 **+08:00**（不是 UTC `Z`，App 端少一次換算就少一個出錯點）。
- **缺 `DTEND` 的 4 筆** → `end = start`（全天則 `end_date = start_date`）。
- 檔案層宣告 `range_end_semantics: "inclusive"`，與契約三同一個字眼。**全檔只有一種語意，不混用。**

**`summary` 逐字保留，不做任何正規化**（不 trim 全形空白、不 pangu、不改標點）。理由見 #181：
App 端有三處靠中文關鍵字反推語意。長期解法是改讀契約三的結構化欄位（見 §4），但在那之前措辭一改就靜默失效，
發布端不能再加一層自己的改寫。

**`uid` 是主鍵**。ics 的 UID 兩種格式（`<base32>@google.com` 341 筆、`CSVConvert<hex32>` 320 筆）都穩定且全筆都有。
App 現行 SwiftData 主鍵 `"cal_<eventId>"`（`SwiftDataModels.swift:688-692`）在沒有數字 id 時會退化成 `"cal_<epoch>_<title>"`，
改用 `uid` 就沒有這個問題。**ics 沒有 `calColor` 的對應物**，`ParsedCalendarEvent.color` 會是空的，由 App 端決定怎麼呈現。

### 排序與變更偵測

**`VEVENT` 排列順序不穩定** —— 同一份連抓兩次順序不同（只有 DTSTAMP 與排序變）。所以：

- 輸出**一律按 `(start, uid)` 穩定排序**，讓檔案本身可重現。
- **`DTSTAMP` 整個丟掉**，它每次抓都不同、不帶資訊。
- **變更偵測比對正規化後的事件集合，不用檔案 md5**（`source.content_sha256` 就是正規化後的雜湊）。
- 內容沒變就**不重寫 canonical、不重新上傳** —— 避免每天產生無意義的 commit 與 R2 寫入。

### 抓取失敗與空結果

抄 `crawler/ntut_catalog/programs.py:36-40` 的防呆：**解析出 0 筆就拋錯，不讓空結果覆寫既有 canonical**。
ics 無 ETag、順序不穩、又是外部主機，這條特別關鍵。另外設一條下限：
解析結果少於既有 canonical 的 95%（沿用 `QUALITY_MIN_RATIO` 的精神）→ 一樣擋下。

### horizon 監測（發布端做，App 端沒有告警能力）

feed 最遠只到 **2027-07-03**（115 學年度結束），沒有任何 116 學年度資料。依 `CREATED` 分群，
每批對應一個學年度，但**匯入時間沒有固定節奏**：114 學年度提前 5 個月（2025-03）、
112 學年度拖到開學當月（2023-08）**而且分上下學期兩批**（下學期等到 2024-02）。

所以：

- **判準是 `max(DTSTART) >= 次年 6 月`**，不是「有沒有新學年的事件」——「看到新學年出現」不等於「整學年到位」。
- **116 學年度預期落在 2027-03 ~ 2027-08 之間出現**，不要寫死「每年七月檢查」。
- **告警不阻斷發布**：feed 沒有新學年不代表現有資料壞了。作法是 workflow 發 warning + 自動開／更新一個 GitHub issue。
  這跟「不變量不過就阻斷」是兩條不同的線。

學校 API 也是同一個 horizon（同樣最遠 2027-07-03），**這不是換源帶來的新風險**，是本來就存在、只是現在由我們顧。

### 發布端接線（已核實）

照 **standards** 的形狀做（既有的「跨學期 top-level、不進 manifest」先例，`names.json` 同理）：
`canonical/calendar/events.ndjson` → `crawler/ntut_catalog/artifacts.py:165-171` → `infra/publish.py:86-89` 的 top-level glob。

⚠️ **實作時發現名單其實有四份，不是三份**：除了 `artifacts.py:200`（進不進 manifest）、
`publish.py:78`（逐學期白名單）、`publish.py:86-89`（top-level glob）之外，
`.github/workflows/crawl.yml:159-162` 的 **commit 步驟也是指名 glob**
（`'*/catalog.ndjson' '*/classes.json' '*/mprograms.json'`、`'*/enrollment/*.ndjson'`）。
跨學期的 top-level 產物**不吃那些逐學期 glob**，漏加就是「檔案有產出、但永遠不會進 data branch」。
（既有的 `canonical/standards/` 就落在這個洞裡——沒有任何 workflow commit 它。）
canonical 走 NDJSON 的好處是 **`data` branch 的 commit 歷史就是「行事曆改了什麼」的免費稽核軌跡** ——
颱風假、補課日這種臨時異動會自己留痕（注意 canonical 不在 main，`data/` 在 `.gitignore:32`，
workflow 用 `actions/checkout@v4 ref: data` 掛進來，見 `.github/workflows/crawl.yml:43-47`）。

抓取掛在 **`crawl.yml` 每日 cron**（`0 20 * * *`，台北 04:00）。每日一次正好回應 #181 對 App 端
30 天 TTL 的批評（`CalendarViewModel.swift:258-274`）：學校臨時改行事曆最多隔一天就到 CDN，
App 再以 ETag 每日檢查一次即可。

ics 解析本身不必從零寫：`docs/research/assets/2026-09-16-calendar-ics-evaluation/scripts/ics_lib.py` 已經處理好全天／有時刻／缺 `DTEND` 三種形態，可直接移植進 `crawler/`（原檔是調查用腳本，移植時補型別與測試）。

**唯一要新寫的基礎件是打外部主機的 HTTP client** —— `CatalogClient` 綁死學校
（`crawler/ntut_catalog/client.py:22` 寫死 base_url、`:28,101` 用學校錯誤頁的中文字串判重試，因為學校的錯誤頁是 HTTP 200），
不能直接拿去打 Google Calendar。寫一支薄的即可，沿用既有的退避與 UA 慣例。

## 6. 契約五：HTTP／CDN 行為

**現況（已核實，讀 repo）**：`infra/publish.py:29-42` 逐物件設 Cache-Control —— `manifest.json`／`enrollment.json` 是 `public, max-age=300`，其餘 `public, max-age=3600`，`:30` 的註解明說「靠 sha + ETag 304」。`infra/r2-cors.json` 已 `exposeHeaders: ["ETag"]`（`origins` 只列 `course.ntutbox.com` 與 `localhost:3000`；iOS `URLSession` 不送 Origin，CORS 不影響 App）。

| 物件 | 建議 Cache-Control | 理由 |
|---|---|---|
| `course/{id}.json` | `public, max-age=3600, stale-while-revalidate=86400` | 週更；SWR 給瀏覽器／CDN，App 自己管 last-known-good |
| `terms/{term}/calendar.json` | `public, max-age=86400, stale-while-revalidate=604800` | 一學期最多修訂一兩次，但**不可宣稱 immutable**（開學前會有修正版）。要在 `infra/publish.py:29-42` 新增一條 |
| `calendar/events.json` | `public, max-age=3600`（**沿用現行預設值，不必加設定**） | 每日重抓；颱風假／補課這種臨時異動要快到使用者手上，不宜比 1 小時更久 |

**ETag／304**：R2 對非 multipart 物件回 MD5 ETag、`If-None-Match` 回 304 是原生行為，但我**沒有實測**（只有 repo 註解與 CORS 設定佐證意圖）。**需實作者查證**：`curl -I` 取 ETag，再帶 `If-None-Match` 必須拿到 304 且 body 為空。

**bot 防護（已核實，2026-09-05 實測）**：同一個 CDN URL，Python `urllib` 預設 UA 直接回 **403**；`curl` 與帶一般 UA 的 urllib 回 200。這是個沒有錯誤訊息的失敗模式。要求兩件事：

- **App 的 User-Agent 約定為 `NTUTBox/<version> (iOS; +https://ntutbox.com)`**，請加一條 Cloudflare WAF skip rule 放行這個 UA 前綴（至少要確認預設 bot 防護不擋 `URLSession` 預設 UA）。
- **403 與 404 語意不可混用**：404 = 這門課沒有 detail（正常，App 顯示「未提供」）；403 = 被防護擋下（App 記 log、保留 last-known-good，**不可**顯示成「教師未提供」）。發布端不要用 403 表達「找不到」。

**需實作者查證**：R2 custom domain 前面現行掛了哪些 Cloudflare 規則（Bot Fight Mode／WAF managed rules），以及能否對特定 UA 放行。我沒有 dashboard 存取權。

## 7. 契約六：`syllabi[]` 的 pass-through 欄位（**2026-09-20 新增**）

**適用欄位**：`Syllabus.flex_learning`（彈性學習 17-18 週）與 `Syllabus.extra`（來源新增的未知標籤欄）。
兩者都是「**上游決定欄位**」的袋子：欄位名由校方的 HTML 表格決定，發布端原樣搬運。

### 形狀（schema v3 起）

```json
"flex_learning": [
  {"label": "類別",       "value": "● 學生分組實作及討論…"},
  {"label": "內容",       "value": "第17週\n類別：參與課程相關作業(口試)…"},
  {"label": "時數(小時)", "value": "4"},
  {"label": "學習成果",   "value": "…"},
  {"label": "評量比例",   "value": "…"}
]
```

`extra` 同形。沒有內容時是 `[]`（不是 null、不是缺欄）。

### 不變量（App 可以依賴）

| 不變量 | 意思 |
|---|---|
| **有序** | 陣列順序＝來源表格列序。跑一遍陣列、`label` 當列標題、`value` 當內容即可。 |
| **`value` 非空白** | 發布端已濾掉空值列，App 不必再過濾一次。 |
| **`label` 可能重複** | 來源把同一欄拆成 17／18 兩列就會發生。**不可當 key、不可塞進 `Dictionary`**。 |
| **欄位名原樣** | 不映射、不正規化。校方改名（已發生過：`課程進度` → `課程進度(1-16週)`）或增減欄位時，App 一行都不用改。 |

### 為什麼不是 dict

**Swift 的 `[String: String]` 本質無序**——`JSONDecoder` 解完，來源順序就永久消失了。
這五欄有閱讀順序（類別 → 內容 → 時數 → 成果 → 比例），dict 根本渲染不出來。
另外 dict 遇到重複 `label` 會後者覆蓋前者、**靜默掉一整列**，而且逼 App 列舉中文 key
（「時數(小時)」的半形括號改成全形就會靜默少一欄）。

### 版本與遷移

- `SCHEMA_VERSION` 2 → 3。**讀到比自己認識的更新的版本要降級容忍，不是整包拒收**：
  這個欄位的設計就是為了讓上游改版不必連帶改 App。
- **CDN 上的資料不會在合併當下就換形狀**，而且**當期與歷史學期走的是兩條不同的路**。
  `course/{id}.json` 是 `canonical/{term}/details.ndjson` 的逐行轉寫（`artifacts.py:155-164`，中間只過 `_write_v1_json` → `normalize_pua` 做缺字修復，不碰欄位結構），
  canonical 住在 orphan `data` branch：

  | 學期 | 怎麼換到 v3 | 為什麼 |
  |---|---|---|
  | **當期（115-1）** | `crawl-details` 週更（每週日 cron）重爬後自然換 | 它每次都全量重寫 details.ndjson |
  | **歷史（110-1～114-2）** | **必須跑 `python -m ntut_catalog migrate-details --out data`** | 週更**刻意只跑當期**（`crawl-details.yml:60-62`）；重爬 10 個學期 ≈ **28,977 請求／6.8 小時**打學校的生產系統，為了純機械的形狀轉換不值得 |

  `migrate-details`（`reprocess.py`）是離線、冪等、不重爬的。它**只動 `flex_learning`/`extra` 兩個 key**，
  不走 Pydantic round-trip——`Syllabus` 沒有 `extra="forbid"`，round-trip 會把 model 還不認識的欄位
  （例如尚未併進 main 的 `weekly_progress`，data branch 上已有 2,304 筆）**靜默刪掉**。
  對 11 個學期、29,480 份 syllabi 實跑驗證過：形狀全轉、順序與內容逐項等價、其餘欄位一字不差、`weekly_progress` 全數保留。

  **跑法**（與 `recategorize`／`rematric` 同一套；這幾個離線子命令都沒有對應 workflow，由人手動跑）：

  1. 把 `data` branch checkout 到 `data/canonical`（workflow 的作法，見 `crawl-details.yml:39-43`）
  2. `python -m ntut_catalog migrate-details --out data`（收尾會自己重建本地 v1）
  3. **人工自檢**（手動步驟沒有 CI 守門）：`grep -l '"flex_learning":{' data/canonical/*/details.ndjson`
     應該完全沒有輸出
  4. commit 回 `data` branch → 跑 `publish-v1`（輸入名是 `include_details`）
- 歷史學期的 `flex_learning` 原本全是 `{}`（彈性學習是 115 學年度才有的政策）。
  **「反正是空的」不是可以不遷移的理由**——`{}` 與 `[]` 對 Swift 的 `Codable` 是不同型別，
  嚴格 decoder 會整筆解碼失敗，而不是得到一個空陣列。
- 在資料換完之前線上仍是 v2 的 dict。App 若要在窗口期內上線，decoder 得兩種都吃；
  Web 端已經是兩種都吃（`CourseDetailContent.tsx` 的 `normalizeFlexRows`）。

### 契約樣本

`crawler/tests/fixtures/contract/course-detail-115-1.json`——與 CDN 的 `course/{id}.json` 同形，
三位教師涵蓋三種形態：①完整彈性學習（五欄）②沒有彈性學習（`[]`）③重複 `label` + 非空 `extra`。
樣本由現行 parser 產出並在 `crawler/tests/test_contract_fixtures.py` 比對，不會靜默過期。
識別碼是佔位值，細節見同目錄的 `README.md`。

## 8. 驗收與契約測試

**Schema 走既有流程**：`crawler/models.py` → `python packages/schema/generate.py` → `packages/schema/schema.json` → `pnpm generate` → `index.d.ts`。`CourseDetail` 已在 `packages/schema/generate.py:17-27` 的 `ROOTS` 裡，所以 `weekly_progress` 一加就自動出現；**calendar 與 calendar-events 是兩個新 root，要自己加進 `ROOTS`**（`packages/schema/generate.py:17-27`）。

App 端會手寫 Swift `Codable` 對照 fixture 做雙邊契約測試，請提供以下 fixture，放在 `crawler/tests/fixtures/weekly_progress/`：

| 檔名 | 內容 |
|---|---|
| `course-resolved.json` | 單 syllabus、18 週全 resolved |
| `course-partial.json` | 部分週 missing ＋ 一則 notes（用 `360986` 的「第4週後需自行規劃」樣態） |
| `course-unparsed.json` | `schedule` 非空但被拒絕（純編號清單樣態） |
| `course-multi-syllabus.json` | 兩位教師、兩份 `weekly_progress` 且內容衝突 |
| `calendar-115-1.json` | 逐學期 calendar 契約樣本，含 `midterm` 與 provenance（放 `crawler/tests/fixtures/calendar/`） |
| `events-sample.json` | 契約四 events feed 契約樣本，**四種事件形態各一**：全天單日／全天跨日／有時刻／缺 `DTEND`（#181 驗收條件第 3 條） |

fixture 用校方公開的課程目錄資料即可（課名／教師名不是個資，見 CLAUDE.md 公開 repo 守則），但**不得含學號、個人 session 或任何帳號衍生物**。

**先講一件會讓「CI 必跑」變成空話的事（2026-09-16 勘查）**：`grep -rn "pytest" .github/workflows/` **零命中** —— 6 支 workflow 全是爬蟲／發佈，也沒有 `.pre-commit-config.yaml` 或任何其他 CI。**現在沒有任何自動閘門會跑 pytest 或 `packages/schema` 的型別生成。**

所以本節的測試要分兩類看：

- **掛在發佈路徑上的**（`quality_gate`、§4 的 10 條不變量、空結果防呆）—— 每次 workflow 跑爬蟲就會跑，**這些是真的閘門**。
- **只存在於 pytest 的**（parser 回歸、fixture 契約測試）—— **目前沒有東西會執行它們**。

→ **本輪要一併加一支 `test.yml`**（push / PR 觸發，跑 `cd crawler && pytest` ＋ 檢查 `packages/schema` 產物沒有未提交的 diff）。沒有這支，下面列的測試寫了也只是文件。§4 不變量⑩ 因此**同時**掛在發佈路徑上，不只放 pytest。

**CI 要加的測試**：`crawler/tests/test_parse_progress.py`（POC 的 `fixtures/gold_cases.json` ＋ 7 個 observed 樣本 ＋ 三條新規則的**接受與拒絕**案例，拒絕案例同等重要）；`crawler/tests/test_term_calendar.py`（§4 的 **10 條不變量** ＋ **111～115 十個學期對照 `docs/research/assets/2026-09-16-term-week-table-from-ics/pdf-week-tables-111-115.json` 的逐筆回歸** ＋ 115 學年度對照 `term-calendar-115.json`）；`crawler/tests/test_calendar_events.py`（ics 解析：全天 end-exclusive 轉 inclusive、缺 `DTEND`、有時刻事件時區、排序穩定性、**空結果不得覆寫既有 canonical**、horizon 判準）；`crawler/tests/test_artifacts.py` 加一條（`weekly_progress` 確實出現在 `v1/terms/{term}/course/{id}.json`）；§3 表格的回歸數字門檻跑在同一支 CI。

### 一個順帶發現：已發布的課綱文字裡有教師個人 email

建語料時掃到 115-1 的 `schedule` 自由文字內含 **10 個 email，其中 8 個是個人 gmail**
（不是校內信箱），是教師自己寫進課程進度裡的。

這不是本輪造成的：`details.ndjson` 早就連同這些文字一起發佈到
`cdn.ntutbox.com/course/v1/terms/{term}/course/{id}.json`。本輪只在**新增的測試語料**裡遮罩。

**`infra/redline_scan.py` 目前沒有 email 規則**，所以這類內容不會被現有閘門擋下。要不要處理
是產品／隱私決定，不是實作細節，留給使用者判斷：
- 加 email 規則到 `redline_scan` 的自由文字規則 → 每日管線會立刻紅（既有資料就含 email），
  等於同時要決定「發布前是否從課綱文字剝除 email」。
- 或維持現狀（視為校方公開課綱的一部分）。

## 9. 明確非目標

- **Edge API**。靜態 CDN 就夠（`ntutbox-edge` 現況只有 AASA 與 `/share/{id}`、沒有 R2 binding，要做等於從零加）。
- **任何登入**。資料源是公開免登入的 `aps.ntut.edu.tw/course/tw/`，消費端也不登入。
- **解析行事曆 PDF**（2026-09-16 起）。週次表改由 ics 推導，PDF 只留在 `docs/research/assets/` 當回歸 fixture 的來源證據，**不進執行期**。
- **App 端的 `CalendarClient` 換源實作**（poterpan/NTUTBox#181）與**週次表遠端來源實作**（#168）。本文只負責發布端；App 端由使用者本人實作。
- **修 #180**。那是現況 bug，與換源獨立。
- **gold set 阻擋上線**（§3）；**App 端的開關、UI、快取策略**；**用模型補寫教師沒提供的進度**（模型最多進 review queue，不得寫進發布資料）。

## 10. 參考與來源清單

**本 repo（已核實行號）**：`crawler/models.py:264-286`（`Syllabus`）、`:272`（`schedule  # 課程進度`）、`:289-302`（`CourseDetail`）、`:473-479`（`ManifestTerm`）、`:248-261`（`LabeledValue`）；`crawler/ntut_catalog/parse_detail.py:15-27`（`_SYLLABUS_LABELS`，`:17` 是課程進度）、`:32-50`（`_match_label` 前綴比對；`:35-36` 記著 2026-08 學校把標籤改成「課程進度(1-16週)」害線上壞掉的教訓）；`crawler/ntut_catalog/detail.py:20`（`crawl_detail`）；`crawler/ntut_catalog/artifacts.py:155-164`、`:192-216`（`write_manifest`，`:200` 的檔名清單目前不含 detail 與 calendar）；`crawler/ntut_catalog/cli.py:108-110`；`infra/publish.py:29-42`、`:45`；`infra/r2-cors.json`；`packages/schema/generate.py:17-27`。

**POC**（`/Users/poterpan/Documents/Coding/NTUT/ntut-course-progress-poc`）：`course_progress_poc/parser.py:73-89`（`WeekSegment`）、`:235`（`parse_schedule`）、`:292-320`（`resolve_week` 三態）；`docs/POC_FINDINGS.md`（6 條陷阱）；`fixtures/observed_115-1_range_cases.json`；`snapshots/115-1-poc-report.json`。

**行事曆（2026-09-16 更新）**：

- 資料源 ics：`https://calendar.google.com/calendar/ical/docfuhim9b22fqvp2tk842ak3c%40group.calendar.google.com/public/basic.ics`
- **換源評估**（覆蓋率、HTTP 標頭、horizon、學校 API 的壞資料）：`docs/research/assets/2026-09-16-calendar-ics-evaluation/`（含 README、比對報告、ics 快照、可重跑腳本）。`raw/cal-raw-threeyear.json` 需登入才抓得到，**別刪**
- **週次表可由 ics 推導的證據**：`docs/research/assets/2026-09-16-term-week-table-from-ics/`（10 學期比對表、萃取腳本、111～115 來源 PDF 與 sha256）
- issue：poterpan/NTUTBox#181（換源，主要）、#168（週次表接 CDN，App 端消費規格與驗收條件）、#180（已修的零長度事件 bug，背景）
- 歷史參考：`NTUT_Tools/docs/research/snapshots/term-calendar-115.json`（人工核對過，`midterm` 漏收）、`NTUT_Tools/docs/research/2026-09-01-course-progress-investigation.md` 第 3 節
- 官方 PDF `https://oaa.ntut.edu.tw/var/file/8/1008/img/2878/{YYY}Calendar.pdf`、列表頁 `https://oaa.ntut.edu.tw/p/412-1008-12781.php?Lang=zh-tw`（2026-09-16 實測當日只掛 112～115）—— **僅供追溯，不再是執行期依賴**

**發布管線（2026-09-16 勘查，已核實行號）**：`crawler/ntut_catalog/cli.py:77`（argparse 進入點）、`:194-222`（mprograms／standards 兩支最該照抄的 CLI）；`crawler/ntut_catalog/programs.py:36-40`（空結果不覆寫的防呆）、`:87-106`（standards 抓取器）；`crawler/ntut_catalog/client.py:22,28,101`（`CatalogClient` 綁死學校，需另寫外部 client）；`crawler/ntut_catalog/artifacts.py:151-154`（逐學期複製）、`:165-171`（top-level 複製）、`:200`（manifest 檔名清單）；`infra/publish.py:45-51,227-237`（quality_gate 是 pre-flight，擋下時一個 byte 都沒上傳）、`:78`（逐學期白名單）、`:86-89`（top-level glob）；`infra/redline_scan.py`（既有的個資／機密／錯誤頁掃描，命中 exit 1 擋 commit，掛在 `crawl.yml:130-131`；`details.ndjson` 與 `course/` 視為自由文字、放寬兩條規則，見 `redline_scan.py:27-29`）；`crawler/pyproject.toml:24-25`（pytest `testpaths`）、`crawler/tests/conftest.py:7`（把 repo 根加進 `sys.path`）、`crawler/tests/_fakes.py:21-40`（**手刻 FakeClient 回放 fixture，repo 不用 mock 套件**）；`.github/workflows/crawl.yml:6-7`（每日 cron）、`:22-24`（concurrency 序列化）、`:43-47`（canonical 掛 `data` branch）。

**App 端 Phase 1（欄位對齊用）**：`NTUTBox/Models/AcademicTermCalendar.swift:22-64`、`NTUTBox/Services/TermCalendarProvider.swift:119-163`、`docs/plans/2026-09-05-semester-week-progress.md`。

| 數字 | 值 |
|---|---:|
| 115-1 開課實例 | 2,461 |
| 有非空課程進度 | 1,886（76.64%） |
| lookup cells resolved | 18,735 / 39,654（47.25%） |
| lookup cells ambiguous | 734（1.85%） |
| 任一週能顯示 topic（推算 76.64% × 47.25%） | 約 **36%** |
| 覆蓋率分布 | **雙峰**：0 週 = 1,011 筆、18 週 = 634 筆（要嘛整表都在、要嘛完全沒有） |
| 多教師且進度衝突的開課實例 | **112** |
| 使用者本人 5 門課實測（114-2） | POC 現況 **1/5** → 加雙語配對 2/5 → 再加編號／日期規則 **3/5** |

5 門樣本太小、不是統計結論，但方向明確：**兩條確定性規則就能把體驗從「大多數課沒東西」翻成「多數課有東西」，而且都不需要模型。**
