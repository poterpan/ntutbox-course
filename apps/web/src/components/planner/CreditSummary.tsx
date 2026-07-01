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

  return (
    <GlassBar className="mx-3 mb-3 flex items-center gap-4 rounded-2xl px-5 py-2.5 text-xs sm:mx-4">
      <div className="flex items-baseline gap-1.5">
        <span className="font-medium text-[var(--ink-soft)]">第一志願學分</span>
        <b className="text-xl font-bold tabular-nums text-[var(--accent-ink)]">{s.firstChoiceCredits}</b>
      </div>
      <span className="h-4 w-px bg-black/15" />
      <span className="font-medium tabular-nums text-[var(--ink-soft)]">
        排入 {placed.length} 門 · {s.placedCredits} 學分
      </span>
      <span
        className={
          "ml-auto flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium tabular-nums " +
          (s.conflictGroupCount > 0 ? "bg-orange-500/15 text-orange-600" : "text-[var(--ink-soft)]")
        }
      >
        衝堂 {s.conflictGroupCount}
      </span>
      {s.unknownCreditCount > 0 && (
        <span className="text-[11px] tabular-nums text-[var(--ink-faint)]">學分未知 {s.unknownCreditCount}</span>
      )}
      <button
        type="button"
        onClick={handleSharePlan}
        disabled={placed.length === 0}
        aria-label="分享課表"
        className="flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-semibold text-[var(--accent)] transition-colors hover:bg-[var(--accent)]/10 disabled:opacity-40 disabled:hover:bg-transparent"
      >
        <svg className="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden>
          <path d="M12 3v12" strokeLinecap="round" />
          <path d="M8 7l4-4 4 4" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" strokeLinecap="round" />
        </svg>
        分享
      </button>
    </GlassBar>
  );
}
