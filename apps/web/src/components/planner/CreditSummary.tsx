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
    <GlassBar className="flex items-center justify-around text-xs">
      <span>第一志願學分：<b>{s.firstChoiceCredits}</b></span>
      <span className="text-zinc-500">排入 {placed.length} 門（{s.placedCredits} 學分）</span>
      <span className={s.conflictGroupCount > 0 ? "text-orange-600" : "text-zinc-500"}>
        衝堂 {s.conflictGroupCount}
      </span>
      {s.unknownCreditCount > 0 && (
        <span className="text-zinc-400">學分未知 {s.unknownCreditCount}</span>
      )}
    </GlassBar>
  );
}
