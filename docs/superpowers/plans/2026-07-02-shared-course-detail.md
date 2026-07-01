# 分享課表 — 點課看詳情 + 收藏/排入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 `SharedTimetableModal` 裡的課程可點開就地詳情，並可收藏 / 排入。

**Architecture:** 把 `CourseDetailDrawer` 的內容（頭部 + 詳情 body + 收藏/排入 footer）抽成共用元件 `CourseDetailContent`；抽屜改成只是它的 Dialog 外殼（行為不變）；`SharedTimetableModal` 加 `detailId` state，在同一個 DialogContent 內 master↔detail 切換、不開新 dialog。

**Tech Stack:** Next.js 16（static export）、React 19、TypeScript、Tailwind v4、Zustand（draft-store / ui-store / term-store）、base-ui Dialog、lucide-react。

## Global Constraints

- **不新增依賴**；圖示用 lucide（`*Icon` 慣例）。
- 色彩/圓角走 `apps/web/AGENTS.md` 設計規範 token（`--ink*` / `--accent` / `--accent-ink`；警示用 `orange-600`），勿用 raw palette 當強調。
- **`CourseDetailDrawer` 對外行為必須完全不變**（載入 effect、`useTouchScrollFocus` 觸控捲動聚焦、分享、收藏/排入/退選狀態）。
- **不動**分享彈窗的「合併/取代」匯入區。
- 驗證方式：`npm run lint` / `npx tsc --noEmit` / `npm test`（現有 109 不退）/ `npm run build` 全綠 ＋ chrome-devtools 目視（393 + 1280）。本功能為 UI 重構/接線、無新增純邏輯，**不新寫元件單元測試**（專案未設置 RTL；假測試無價值），沿用專案「綠測試≠完成、以實際畫面驗收」慣例。
- 指令都在 `apps/web/` 下執行。

---

### Task 1: 抽出 `CourseDetailContent`，抽屜改用它（行為不變）

**Files:**
- Create: `apps/web/src/components/planner/CourseDetailContent.tsx`
- Modify: `apps/web/src/components/planner/CourseDetailDrawer.tsx`（整檔重寫成薄外殼）

**Interfaces:**
- Produces:
  - `CourseDetailContent(props: { offeringId: string; onAfterPlace?: () => void; headerLeading?: React.ReactNode; scrollRef?: React.Ref<HTMLDivElement> }): JSX.Element | null`
    - 自行以 `byId(offeringId)` 取課；查不到回傳 `null`。
    - 渲染：頭部（`headerLeading` slot ＋ 課名 `<h2>` ＋ 學分/選別/語言 badges ＋ 分享鈕）＋ 可捲動 body（資訊列 + 備註 + 概述 + 教學大綱 + 載入/空狀態）＋ footer（收藏 toggle + 排入/退選）。
    - `onAfterPlace`：排入或退選後呼叫（抽屜傳 `() => openDetail(null)`）。收藏 toggle **不**呼叫。
    - `scrollRef`：掛到 body 捲動容器（抽屜傳 `useTouchScrollFocus().scrollRef`）。

- [ ] **Step 1: 建立 `CourseDetailContent.tsx`**

把「現有 `CourseDetailDrawer.tsx` 的內部實作」搬進來、參數化差異。完整檔案內容：

```tsx
"use client";
import { useEffect, useState } from "react";
import { ShareIcon } from "lucide-react";
import { AccentButton } from "@/components/ui/accent-button";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";
import { getDataSource } from "@/lib/data";
import { buildCourseLink } from "@/lib/share/course-link";
import { shareOrCopy } from "@/lib/share/share-course";
import { useToast } from "@/components/ui/toast";
import type { CourseDetail } from "@/lib/data/types";
import { resolveMatric } from "@/lib/planner/matric";
import { cn } from "@/lib/utils";

const DAY = ["日", "一", "二", "三", "四", "五", "六"];

const SYLLABUS_FIELDS: [keyof NonNullable<CourseDetail["syllabi"]>[number], string][] = [
  ["outline", "課程大綱"],
  ["schedule", "課程進度"],
  ["assessment", "評量方式"],
  ["materials", "教材／參考書"],
  ["consultation", "課程諮詢"],
  ["extended_resources", "延伸教學與資源"],
  ["sdgs", "對應 SDGs"],
  ["ai_usage", "AI 導入"],
  ["notes", "備註"],
];

export function CourseDetailContent({
  offeringId,
  onAfterPlace,
  headerLeading,
  scrollRef,
}: {
  offeringId: string;
  onAfterPlace?: () => void;
  headerLeading?: React.ReactNode;
  scrollRef?: React.Ref<HTMLDivElement>;
}) {
  const { byId, enrollment } = useTermCourses();
  const termKey = useTermStore((s) => s.termKey);
  const { favorites, placed, place, unplace, toggleFavorite } = useDraftStore();
  const showToast = useToast((s) => s.show);
  const c = byId(offeringId);
  const isFav = c ? favorites.includes(c.offering_id) : false;
  const isPlaced = c ? placed.some((p) => p.offering_id === c.offering_id) : false;
  const e = c ? enrollment[c.offering_id] : undefined;
  const division = c ? resolveMatric(c) : null;

  const [detail, setDetail] = useState<CourseDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    if (!offeringId || !termKey) return;
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoadingDetail(true);
    setDetail(null);
    getDataSource()
      .getCourseDetail(termKey, offeringId)
      .then((d) => { if (alive) setDetail(d); })
      .catch(() => { if (alive) setDetail(null); })
      .finally(() => { if (alive) setLoadingDetail(false); });
    return () => { alive = false; };
  }, [offeringId, termKey]);

  if (!c) return null;

  const desc = detail?.description;
  const syllabi = detail?.syllabi ?? [];

  async function handleShare() {
    if (!c || !termKey) return;
    const url = buildCourseLink({ termKey, offeringId: c.offering_id, origin: window.location.origin });
    const name = c.name.zh ?? "課程";
    const r = await shareOrCopy(url, name, `${name}｜北科盒子 排課`);
    if (r === "copied") showToast("已複製連結");
    else if (r === "failed") showToast("複製失敗，請手動複製網址");
  }

  return (
    <>
      <div className="border-b border-black/5 px-6 py-4">
        <div className="flex items-start gap-2">
          {headerLeading}
          <h2 className="text-xl font-bold text-[var(--ink)]">{c.name.zh}</h2>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[var(--ink-soft)]">
          <Badge>{c.credits ?? "?"} 學分</Badge>
          {c.requirement?.symbol && <Badge>{c.requirement.symbol}</Badge>}
          {c.language && <Badge>{c.language}</Badge>}
          <span>課號 {c.offering_id}</span>
          {c.course_code && <span>· 編碼 {c.course_code}</span>}
          <button
            type="button"
            aria-label="分享此課程"
            onClick={handleShare}
            className="ml-auto flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 font-medium text-[var(--accent)] transition-colors hover:bg-[var(--accent)]/10"
          >
            <ShareIcon className="size-3.5" aria-hidden />
            分享
          </button>
        </div>
      </div>

      <div ref={scrollRef} tabIndex={-1} className="thin-scroll flex-1 overflow-y-auto overscroll-contain px-6 py-5 outline-none [touch-action:pan-y]">
        <dl className="grid grid-cols-1 gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
          <Row k="授課教師" v={(c.teachers ?? []).map((t) => t.name).join("、") || "—"} />
          <Row k="學制" v={division?.label ?? "—"} />
          <Row k="開課單位" v={c.unit_name ?? "—"} />
          <Row k="開課班級" v={(c.classes ?? []).map((k) => `${k.name}${k.kind === "pool" ? "(池)" : k.kind === "virtual" ? "(佔位)" : ""}`).join("、") || "—"} />
          <Row k="時數" v={c.hours != null ? String(c.hours) : "—"} />
          <Row k="上課時間" v={(c.meetings ?? []).map((m) => `週${DAY[m.day]} ${m.periods.join("、")}節`).join("；") || "—"} />
          <Row k="教室" v={(c.classrooms ?? []).map((r) => r.name).join("、") || "—"} />
          <Row k="已選人數" v={e?.enrolled_count != null ? String(e.enrolled_count) : "—"} />
          {c.tags && c.tags.length > 0 && <Row k="標籤" v={c.tags.join("、")} />}
        </dl>

        {c.notes_raw && (
          <Section title="備註">
            <p className="whitespace-pre-wrap text-sm text-[var(--ink)]">{c.notes_raw}</p>
          </Section>
        )}

        {desc?.zh && (
          <Section title="課程概述">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--ink)]">{desc.zh}</p>
          </Section>
        )}

        {syllabi.length > 0 && (
          <Section title="教學大綱">
            <div className="space-y-4">
              {syllabi.map((s, i) => (
                <div key={i} className="rounded-xl bg-black/[0.025] p-4">
                  <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="text-sm font-semibold text-[var(--ink)]">{s.teacher_name || "教師"}</span>
                    {s.email && (
                      <a href={`mailto:${s.email}`} className="text-xs text-[var(--accent-ink)] hover:underline">{s.email}</a>
                    )}
                    {s.updated_at && <span className="text-[10px] text-[var(--ink-faint)]">更新 {s.updated_at}</span>}
                  </div>
                  <dl className="space-y-2.5">
                    {SYLLABUS_FIELDS.map(([key, label]) => {
                      const val = s[key];
                      return typeof val === "string" && val.trim() ? (
                        <div key={key}>
                          <dt className="text-[11px] font-semibold uppercase tracking-wide text-[var(--ink-soft)]">{label}</dt>
                          <dd className="mt-0.5 whitespace-pre-wrap text-sm leading-relaxed text-[var(--ink)]">{val}</dd>
                        </div>
                      ) : null;
                    })}
                  </dl>
                </div>
              ))}
            </div>
          </Section>
        )}

        {loadingDetail && !desc && (
          <p className="mt-5 text-sm text-[var(--ink-soft)]">載入課程概述與大綱中…</p>
        )}
        {!loadingDetail && !desc?.zh && syllabi.length === 0 && (
          <p className="mt-5 rounded-xl bg-black/[0.03] px-3 py-3 text-sm text-[var(--ink-soft)]">
            本課程暫無課程概述／教學大綱資料。
          </p>
        )}
      </div>

      <div className="flex items-center gap-2 border-t border-black/5 px-6 py-4">
        <button
          type="button"
          onClick={() => toggleFavorite(c.offering_id)}
          className={cn(
            "flex items-center gap-1.5 rounded-xl border px-4 py-2.5 text-sm font-medium transition-colors",
            isFav ? "border-amber-300 bg-amber-50 text-amber-600" : "border-black/10 bg-white text-[var(--ink)] hover:bg-black/5",
          )}
        >
          {isFav ? "★ 已收藏" : "☆ 收藏"}
        </button>
        {isPlaced ? (
          <button
            type="button"
            onClick={() => { unplace(c.offering_id); onAfterPlace?.(); }}
            className="ml-auto rounded-xl border border-red-200 bg-red-50 px-5 py-2.5 text-sm font-semibold text-red-600 transition-colors hover:bg-red-100"
          >
            退選（從課表移除）
          </button>
        ) : (
          <AccentButton
            size="lg"
            className="ml-auto"
            onClick={() => { place(c.offering_id); onAfterPlace?.(); }}
          >
            ＋ 排入課表
          </AccentButton>
        )}
      </div>
    </>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-3">
      <dt className="w-20 shrink-0 text-[var(--ink-soft)]">{k}</dt>
      <dd className="min-w-0 flex-1 text-[var(--ink)]">{v}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-5">
      <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--ink-soft)]">{title}</h3>
      {children}
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="rounded-md bg-[var(--accent)]/10 px-1.5 py-0.5 text-[11px] font-medium text-[var(--accent-ink)]">{children}</span>;
}
```

> 說明：頭部原本用 `DialogTitle` 當課名；抽出後改為一般 `<h2>`（a11y 的 DialogTitle 由外殼負責）。footer 的排入/退選改呼叫 `onAfterPlace?.()`（原本抽屜寫死 `openDetail(null)`）。其餘（資訊列、備註、概述、大綱、載入/空狀態、`Row`/`Section`/`Badge`）與現行完全相同。

- [ ] **Step 2: 重寫 `CourseDetailDrawer.tsx` 成薄外殼**

完整檔案內容：

```tsx
"use client";
import { DialogPrimitiveTitle } from "@/components/ui/dialog";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { CourseDetailContent } from "./CourseDetailContent";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useUiStore } from "@/store/ui-store";
import { useTouchScrollFocus } from "@/lib/planner/use-touch-scroll-focus";

export function CourseDetailDrawer() {
  const { byId } = useTermCourses();
  const { detailOfferingId, openDetail } = useUiStore();
  const c = detailOfferingId ? byId(detailOfferingId) : undefined;
  const { scrollRef, initialFocus } = useTouchScrollFocus();

  return (
    <Dialog open={!!c} onOpenChange={(o) => { if (!o) openDetail(null); }}>
      <DialogContent initialFocus={initialFocus} className="flex h-[88vh] w-[94vw] max-w-[94vw] flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
        {c && (
          <>
            <DialogPrimitiveTitle className="sr-only">{c.name.zh}</DialogPrimitiveTitle>
            <CourseDetailContent
              offeringId={c.offering_id}
              scrollRef={scrollRef}
              onAfterPlace={() => openDetail(null)}
            />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

> 注意：`DialogPrimitiveTitle` 是 a11y 用的 sr-only 標題。**先檢查** `apps/web/src/components/ui/dialog.tsx` 實際 export 名稱 — 若只有 `DialogTitle`，就用 `import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";` 並把 sr-only 那行寫成 `<DialogTitle className="sr-only">{c.name.zh}</DialogTitle>`（見 Step 3）。

- [ ] **Step 3: 確認 `DialogTitle` 匯出名稱、修正 import**

Run: `grep -n "export" apps/web/src/components/ui/dialog.tsx`
Expected: 看到 `DialogTitle`（base-ui 包裝）。→ 把 Step 2 的 `DialogPrimitiveTitle` 全部改成 `DialogTitle`，import 改 `import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";`。

- [ ] **Step 4: 型別 + lint**

Run: `npx tsc --noEmit && npm run lint`
Expected: 皆無錯誤。

- [ ] **Step 5: build + 現有測試**

Run: `npm test && npm run build`
Expected: 109 tests pass；build green。

- [ ] **Step 6: 目視驗證抽屜「完全沒壞」**

啟 dev server（若未啟），chrome-devtools 開 `localhost:3000/?term=115-1`：
1. 點課程庫任一課列 → 抽屜開、載入資訊/大綱。
2. 點「☆收藏」→ 變「★已收藏」。
3. 點「＋排入課表」→ 抽屜關、課進課表。
4. 再開該課 → footer 顯示「退選」；點退選 → 抽屜關、課移除。
5. 點頭部「分享」→ toast「已複製連結」。
6. 觸控（emulate 手機）body 首次拖曳即可捲動（`useTouchScrollFocus` 沒壞）。

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/components/planner/CourseDetailContent.tsx apps/web/src/components/planner/CourseDetailDrawer.tsx
git commit -m "refactor(web): 抽出 CourseDetailContent，抽屜改用（行為不變）"
```

---

### Task 2: `SharedTimetableModal` 就地詳情（清單列可點 + 收藏/排入）

**Files:**
- Modify: `apps/web/src/components/planner/SharedTimetableModal.tsx`

**Interfaces:**
- Consumes: `CourseDetailContent`（Task 1）。
- 新增 local state `detailId: string | null`；`detailId != null` 時整個 DialogContent 內容改渲染 `CourseDetailContent`（不開新 dialog）。

- [ ] **Step 1: 加 `detailId` state 與詳情 view**

在 `SharedTimetableModal` 元件內、既有 `const [choosing, setChoosing] = useState(false);` 之後加：

```tsx
  const [detailId, setDetailId] = useState<string | null>(null);
```

在既有 import 區加：

```tsx
import { CourseDetailContent } from "./CourseDetailContent";
```

在 `return (<Dialog ...><DialogContent ...>` 內、**最前面**（`<DialogHeader>` 之前）插入詳情分支；用 early branch 包住原本內容。把原本 `<DialogHeader>…</DialogHeader>` + body + 匯入 footer 這三塊維持不變，但整包只在 `!detailId` 時渲染，`detailId` 時改渲染詳情：

```tsx
        {detailId ? (
          <CourseDetailContent
            offeringId={detailId}
            onAfterPlace={() => setDetailId(null)}
            headerLeading={
              <button
                type="button"
                onClick={() => setDetailId(null)}
                aria-label="返回課表"
                className="-ml-1 mr-1 shrink-0 rounded-lg px-2 py-1 text-sm font-semibold text-[var(--accent)] transition-colors hover:bg-[var(--accent)]/10"
              >
                ← 課表
              </button>
            }
          />
        ) : (
          <>
            {/* 原本的 <DialogHeader>…、<div class="…overflow-y-auto…">…、以及底部匯入 <div>… 全部原封不動搬進這個 fragment */}
          </>
        )}
```

> DialogTitle 保留在 `!detailId` 分支的 `<DialogHeader>` 內（維持 dialog 的 a11y 名稱為「分享的課表」）；詳情分支不再另設 DialogTitle（同一 DialogContent 已有一個即可，base-ui 只需掛載時存在其一即滿足——若 dev 警告缺 title，於 detail 分支頂部補一個 `<DialogTitle className="sr-only">課程詳情</DialogTitle>`）。

- [ ] **Step 2: 清單列可點 → 開詳情**

找到既有渲染課程清單的 `validIds.map((id, i) => { ... <li ...>` 區塊，把該 `<li>` 換成可點按鈕列（保留原樣式，加 `onClick`、`cursor-pointer`、hover）：

把原本：
```tsx
                  <li key={id} className="flex items-center gap-2 rounded-lg bg-black/[0.02] px-2.5 py-1.5 text-xs">
```
改成：
```tsx
                  <li key={id}>
                   <button
                     type="button"
                     onClick={() => setDetailId(id)}
                     className="flex w-full items-center gap-2 rounded-lg bg-black/[0.02] px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-black/[0.05]"
                   >
```
並把該 `<li>` 原本的結尾 `</li>` 改成 `</button></li>`（內部 3 個 `<span>` 內容不變）。

- [ ] **Step 3: 型別 + lint**

Run: `npx tsc --noEmit && npm run lint`
Expected: 無錯誤。

- [ ] **Step 4: build + 測試**

Run: `npm test && npm run build`
Expected: 109 pass；green。

- [ ] **Step 5: 目視驗證（393 + 1280）**

chrome-devtools 開 plan 連結 `localhost:3000/?term=115-1&plan=360744.361278.360753`：
1. 分享彈窗開 → 點清單任一課列 → 就地切成詳情（含「← 課表」）。
2. 點「← 課表」→ 回到週課表清單。
3. 詳情點「☆收藏」→ 變「★已收藏」、停留在詳情。
4. 詳情點「＋排入課表」→ 回清單（`setDetailId(null)`）；關掉分享彈窗看主課表已加入該課。
5. 桌機（1280）同樣流程正常。

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/planner/SharedTimetableModal.tsx
git commit -m "feat(web): #32 分享彈窗課程可點看詳情 + 收藏/排入（就地展開）"
```

---

### Task 3: 週課表格子也可點（順手，非必要）

**Files:**
- Modify: `apps/web/src/components/planner/SharedTimetableGrid.tsx`
- Modify: `apps/web/src/components/planner/SharedTimetableModal.tsx`

**Interfaces:**
- `SharedTimetableGrid` 加 optional prop `onCourseClick?: (offeringId: string) => void`；有傳時，格子課塊變成可點、呼叫它。

- [ ] **Step 1: 讀 `SharedTimetableGrid.tsx`，找到課塊渲染處**

Run: `grep -n "offering_id\|onClick\|<div\|<button" apps/web/src/components/planner/SharedTimetableGrid.tsx`
決定課塊元素，加 `onCourseClick?: (offeringId: string) => void` 到 props，課塊包一層 `onClick={() => onCourseClick?.(id)}`（有 handler 時加 `cursor-pointer`）。**若課塊結構複雜/風險高，Task 3 可略過**（清單列已能滿足需求）。

- [ ] **Step 2: `SharedTimetableModal` 傳入 handler**

`<SharedTimetableGrid placed={placed} />` → `<SharedTimetableGrid placed={placed} onCourseClick={setDetailId} />`

- [ ] **Step 3: 型別 + lint + build + 測試**

Run: `npx tsc --noEmit && npm run lint && npm test && npm run build`
Expected: 全綠。

- [ ] **Step 4: 目視 + Commit**

驗證格子可點開詳情。
```bash
git add apps/web/src/components/planner/SharedTimetableGrid.tsx apps/web/src/components/planner/SharedTimetableModal.tsx
git commit -m "feat(web): 分享彈窗週課表格子也可點開詳情"
```

---

## Self-Review

- **Spec coverage**：就地詳情（Task 2）、收藏/排入（Task 1 的 footer + Task 2 接線）、清單列可點（Task 2）、格子可點（Task 3）、抽屜不變（Task 1 Step 6）、不動合併/取代（三個 Task 都沒碰匯入區）、失效課號濾除（沿用既有 `validIds`，不需新 code）。皆有對應。
- **Placeholder scan**：無 TBD；Task 3 明列「可略過」為刻意 YAGNI，非佔位。
- **Type consistency**：`CourseDetailContent` 的 props（`offeringId`/`onAfterPlace`/`headerLeading`/`scrollRef`）在 Task 1 定義、Task 2/抽屜一致使用；`setDetailId: (id: string|null)` 與 `onCourseClick`/`onAfterPlace` 型別相容。
- **風險點**：Task 1 Step 2 的 `DialogTitle` 匯出名稱以 Step 3 grep 確認為準；Task 2 的「原內容原封搬進 fragment」需保留既有 JSX 完全不變。
