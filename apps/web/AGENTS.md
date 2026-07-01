<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

<!-- BEGIN:web-design-system -->
# Web 設計規範（新元件務必沿用；2026-07 收斂，PR #27）

視覺向北科盒子 iOS（Apple / Liquid-Glass）靠攏。**先用共用元件、再談手刻**——歷史教訓是各自手刻 → 樣式漂移。

## Token 是唯一來源（勿用 raw palette）
- 用 glass token：`--ink / --ink-soft / --ink-faint`（文字三階）、`--accent`（填色/主色）、`--accent-ink`（accent 的深色文字，= blue-700）、`--glass-*`。
- **禁止**用 raw Tailwind 色（`blue-100`、`zinc-400`…）當「選取／強調／次要文字」——不吃 dark mode。次要文字：次要用 `--ink-soft`、第三階用 `--ink-faint`。
- `ui/*` 的 shadcn token（`--primary/--muted/--ring`）**沒接** glass；僅 `ui/button` 在低階 wrapper（sheet/dialog/FAB）用，一般 UI 別走它。

## 共用元件（別再手刻 input / chip / 主按鈕）
- `ui/search-input.tsx` — `<SearchInput variant=prominent|inset|popover>`：所有搜尋框。內含 16px 輸入值（防 iOS 聚焦自動放大）、placeholder 14px + `--ink-faint/75`、accent focus ring、放大鏡 icon（prominent）。
- `ui/filter-chip.tsx` — `filterChipVariants({active})` + `<CountBadge>`：rounded-full 篩選 pill。多子元素的 trigger 外加 `inline-flex items-center gap-1.5`。
- `ui/accent-button.tsx` — `<AccentButton tone=solid|soft size=sm|lg>`：accent 行動按鈕（排入=solid、已排=soft，**同尺寸只差色調**；drawer CTA=lg）。

## 選取 / 強調色
- 一律走 accent token：實心 `bg-[var(--accent)] text-white`；淡底 `bg-[var(--accent)]/10~12 text-[var(--accent-ink)]`。
- 相鄰多選合併成群組：只收整段頭尾圓角（見 FilterCombobox 依 run 位置給 `rounded-t/b`）。

## 「已選」表意（別濫用 ✓）
- 多選清單列 → 方塊 checkbox（`rounded-md` 框 + ✓）。
- 切換 chip → **靠填滿 accent 表示選中，不加「✓ 」文字前綴**。
- 多態（如英文授課 含/排除/關）→ `✓`/`✕` 有語意，保留。
- 「已排」等是**狀態**、非選取控制（用 soft tone 呈現）。

## 圓角級距（對齊 Tailwind 預設、依角色套用；勿隨手挑）
| 角色 | class | px |
|---|---|---|
| checkbox / badge | `rounded-md` | 6 |
| 輸入框 / 小按鈕 / 下拉選項列 / 方形 toggle | `rounded-lg` | 8 |
| 卡片 / 課程列 / 大 CTA / prominent 搜尋 | `rounded-xl` | 12 |
| 面板 / Dialog / bottom sheet | `rounded-2xl` 或 `--glass-radius`(22px) | 16–22 |
| chip / 頭像 / 純狀態藥丸 | `rounded-full` | — |

- **圓角隨元件大小成比例**（大元件用大圓角）。
- **同心規則（重要）**：圓角元件放進圓角容器時 `內圓角 ≈ 外圓角 − padding`；違反會「掐腰」（曾出現的 filter row bug 即此）。
- **squircle**：基礎用 `border-radius`（iOS Safari 吃得到）；`corner-shape: squircle` 只 Chromium 支援、僅當漸進增強、**勿依賴**。
<!-- END:web-design-system -->
