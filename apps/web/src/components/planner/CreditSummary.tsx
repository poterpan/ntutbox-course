"use client";
import { useMemo } from "react";
import { useDraftStore } from "@/store/draft-store";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { creditSummary } from "@/lib/schedule/credits";
import { GlassBar } from "@/components/glass/GlassBar";

export function CreditSummary() {
  const placed = useDraftStore((s) => s.placed);
  const { byId } = useTermCourses();
  const s = useMemo(() => creditSummary(placed, byId), [placed, byId]);

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
        <span className="text-[11px] tabular-nums text-zinc-400">學分未知 {s.unknownCreditCount}</span>
      )}
    </GlassBar>
  );
}
