"use client";
import { useMemo } from "react";
import { useDraftStore } from "@/store/draft-store";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { creditSummary } from "@/lib/schedule/credits";
import { GlassBar } from "@/components/glass/GlassBar";
import { useTermStore } from "@/store/term-store";
import { buildPlanLink } from "@/lib/share/plan-link";
import { shareOrCopy } from "@/lib/share/share-course";
import { useToast } from "@/components/ui/toast";
import { AccentButton } from "@/components/ui/accent-button";

export function CreditSummary() {
  const placed = useDraftStore((s) => s.placed);
  const { byId } = useTermCourses();
  const s = useMemo(() => creditSummary(placed, byId), [placed, byId]);
  const termKey = useTermStore((st) => st.termKey);
  const showToast = useToast((st) => st.show);

  async function handleSharePlan() {
    if (!termKey || placed.length === 0) return;
    const offeringIds = [...placed].sort((a, b) => a.priority - b.priority).map((p) => p.offering_id);
    const url = buildPlanLink({ termKey, offeringIds, origin: window.location.origin });
    const r = await shareOrCopy(url, "我的課表", "我的課表｜北科盒子 排課");
    if (r === "copied") showToast("已複製課表連結");
    else if (r === "failed") showToast("複製失敗，請手動複製網址");
  }

  // F-C「匯出到 App」尚未完成 → 先預留按鈕佔位，按下提示即將上線。
  function handleExportSoon() {
    showToast("匯出到 App 功能即將上線");
  }

  return (
    <GlassBar className="mx-3 mb-3 flex flex-col gap-1.5 rounded-2xl px-4 py-2.5 sm:mx-4 sm:flex-row sm:items-center sm:gap-4 sm:px-5">
      {/* 數據列（一行、含顯眼的第一志願學分大數字當錨點）— 固定不與動作同行，避免窄機翻行 */}
      <div className="flex flex-1 flex-wrap items-center gap-x-2.5 gap-y-1 text-xs tabular-nums text-[var(--ink-soft)]">
        <span className="flex items-baseline gap-1.5">
          <span className="font-medium">第一志願學分</span>
          <b className="text-xl font-bold text-[var(--accent-ink)]">{s.firstChoiceCredits}</b>
        </span>
        <span aria-hidden className="text-[var(--ink-faint)]">·</span>
        <span>排入 <b className="font-semibold text-[var(--ink)]">{placed.length}</b> 門 · <b className="font-semibold text-[var(--ink)]">{s.placedCredits}</b> 學分</span>
        <span aria-hidden className="text-[var(--ink-faint)]">·</span>
        <span className={s.conflictGroupCount > 0 ? "font-semibold text-orange-600" : undefined}>衝堂 {s.conflictGroupCount}</span>
        {s.unknownCreditCount > 0 && (
          <>
            <span aria-hidden className="text-[var(--ink-faint)]">·</span>
            <span className="text-[var(--ink-faint)]">學分未知 {s.unknownCreditCount}</span>
          </>
        )}
      </div>

      {/* 動作列：匯出到 App（primary、最終目的；目前預留、按下顯示即將上線）+ 分享（次要 icon）。
          手機撐滿整列、桌機靠右。 */}
      <div className="flex items-center gap-2">
        <AccentButton
          tone="solid"
          size="lg"
          onClick={handleExportSoon}
          className="flex-1 gap-1.5 sm:flex-none"
        >
          <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden>
            <path d="M14 4h6v6" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M20 4 11 13" strokeLinecap="round" />
            <path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          匯出到 App
        </AccentButton>
        <AccentButton
          tone="soft"
          size="lg"
          onClick={handleSharePlan}
          disabled={placed.length === 0}
          aria-label="分享課表"
          className="size-10 shrink-0 justify-center p-0"
        >
          <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden>
            <path d="M12 3v12" strokeLinecap="round" />
            <path d="M8 7l4-4 4 4" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" strokeLinecap="round" />
          </svg>
        </AccentButton>
      </div>
    </GlassBar>
  );
}
