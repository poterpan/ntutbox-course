# 管線 v2 遷移驗證報告（2026-09-26，離線 gate）

> 資料管線重構 Task 4 的 gate（spec §7、plan Task 4）。**結論：通過**——除 spec §6 允許的欄位與
> `weekly_progress` 重算外，兩份 v1 沒有任何差異。這份報告供切換前檢查點 1 使用；
> 切換當天 `maintenance` → `migrate` 會對當時的 data branch 重跑同一套驗證、報告附在 run 上。

## 怎麼驗的

| 項目 | 內容 |
|---|---|
| 資料 | `origin/data` @ `b36c314`（2026-09-26 的完整 data branch，本機兩份獨立複本，**未寫回 origin**） |
| 舊版 v1 | `origin/main` @ `1fb834c` 的程式碼（獨立 worktree＋venv），對**遷移前**複本跑 `derive` → 32,696 檔 |
| 新版 v1 | `refactor/pipeline-v2` 的 `migrate-pipeline-v2 --data canonical`，再 `derive` → 32,696 檔 |
| 比對 | `python infra/verify_migration.py old/v1 new/v1`，逐檔比對；exit 0 |
| 耗時 | 遷移 2.5 秒、新版 derive 17.5 秒（含 3.2 萬份課綱即時算逐週進度）、比對 8 秒 |

允許的差異（其餘必須逐位元組相同）：

- `manifest.json`：新增每個產物的 `checked_at`／`changed_at`、每學期的 `details`；`generated_at`／`published_at` 由 publish 寫入，不比。
- `course/{id}.json`：移除 `generated_at`、`weekly_progress.parsed_at`；`weekly_progress` 內容因重算而不同 → 允許但列報（下表）。
- `enrollment.json`：只允許 JSON 鍵順序不同（實際上連順序都相同，11 份逐位元組相同）。

## 各產物類型變動檔數

| 產物 | 總數 | 相同 | 允許的變動 | 其中 weekly_progress 內容不同 | 不允許 | 只在一邊 |
|---|---:|---:|---:|---:|---:|---:|
| `calendar.json` | 2 | 2 | 0 |  | 0 |  |
| `calendar/events.json` | 1 | 1 | 0 |  | 0 |  |
| `catalog.json` | 11 | 11 | 0 |  | 0 |  |
| `classes.json` | 11 | 11 | 0 |  | 0 |  |
| `course/{id}.json` | 32625 | 0 | 32625 | 20334 | 0 |  |
| `enrollment.json` | 11 | 11 | 0 |  | 0 |  |
| `manifest.json` | 1 | 0 | 1 |  | 0 |  |
| `mprograms.json` | 11 | 11 | 0 |  | 0 |  |
| `names.json` | 11 | 11 | 0 |  | 0 |  |
| `periods.json` | 11 | 11 | 0 |  | 0 |  |
| `standards/*.json` | 1 | 1 | 0 |  | 0 |  |

- `course/{id}.json` 全部 32,625 份都變（每份至少少了 `generated_at`）——切換時 `republish` 預期重傳約 3.3 萬物件，與 spec §8 估計一致。
- 其中 20,334 份的 `weekly_progress` 內容不同，**全部落在 110-1～114-2**：這 10 個學期的舊 canonical 從來沒存過逐週進度，遷移後由 derive 第一次算出來。115-1 一份都沒變（它的 progress 在 09-21 已用現行 parser 重跑過）。
- 其餘產物（catalog／classes／periods／names／mprograms／enrollment／行事曆／events／standards）全部逐位元組相同。

## weekly_progress 各學期 status（遷移前 → 遷移後）

以 syllabus 計，每格依序為 resolved / partial / unparsed / （無）。「（無）」是依課名排除、刻意不算進度的課（`is_progress_excluded`，例如專題類），遷移前後在 115-1 都是 116 份，行為一致。

| 學期 | 遷移前 | 遷移後 | progress 有變的課程檔 |
|---|---|---|---:|
| 110-1 | 0 / 0 / 0 / 2855 | 984 / 271 / 1461 / 139 | 2163 |
| 110-2 | 0 / 0 / 0 / 2798 | 1010 / 284 / 1366 / 138 | 2076 |
| 111-1 | 0 / 0 / 0 / 2793 | 994 / 259 / 1425 / 115 | 2118 |
| 111-2 | 0 / 0 / 0 / 2751 | 1040 / 261 / 1334 / 116 | 2062 |
| 112-1 | 0 / 0 / 0 / 2784 | 1051 / 236 / 1382 / 115 | 2131 |
| 112-2 | 0 / 0 / 0 / 2762 | 1090 / 311 / 1244 / 117 | 2055 |
| 113-1 | 0 / 0 / 0 / 2696 | 1079 / 250 / 1257 / 110 | 2034 |
| 113-2 | 0 / 0 / 0 / 2588 | 1057 / 260 / 1158 / 113 | 1889 |
| 114-1 | 0 / 0 / 0 / 2570 | 1041 / 232 / 1187 / 110 | 1955 |
| 114-2 | 0 / 0 / 0 / 2579 | 1061 / 235 / 1164 / 119 | 1851 |
| 115-1 | 1471 / 224 / 539 / 116 | 1471 / 224 / 539 / 116 | 0 |

這些數字就是 App 課綱頁在切換後會看到的逐週進度——舊學期原本完全沒有，切換後會出現。

## 遷移本身做了什麼（對 `b36c314`）

| 步驟 | 結果 |
|---|---|
| details：去 `generated_at`、`weekly_progress` | 11 個學期的 `details.ndjson` 改寫（以新版 `detail_line` 重新序列化，之後重爬不會只因格式不同而整份變動） |
| enrollment：依列內 `observed_at` 改名、去時間戳、去重、重建觀測紀錄 | 110-1～114-2 各 1 份舊檔 → 1 份快照＋1 筆觀測；115-1 共 144 份舊檔 → **91 份快照**（53 份與前一份相同而刪除）＋**144 筆觀測** |
| `_meta/fetch-state.json` | 新建，46 筆：catalog／mprograms／details／enrollment 各 11 學期，calendar、standards 各 1（`_global`） |
| reports | `reports/115-1/weekly-progress.json` 去 `generated_at`；derive 另為 110-1～114-2 新產出 10 份報告 |
| 冪等 | 遷移後再跑一次：所有檔案 MD5 不變、`changed=false` |

`fetch-state` 的時間取自 git log：`changed_at`＝該資料集內容檔最後一次 commit，`checked_at`＝該資料集全部寫入檔（catalog 含每日人數快照）最後一次 commit；enrollment 鍵與 merge 同算法（`changed_at`＝最新快照檔名時間、`checked_at`＝最後一筆觀測）。例：115-1 catalog `changed_at`＝`checked_at`＝2026-09-26 01:16；calendar 最後一次內容變動 2026-09-20 05:12（舊流程內容沒變就不 commit，所以切換後第一次 daily 會把 `checked_at` 往前推）。

## 不允許的差異

無。
