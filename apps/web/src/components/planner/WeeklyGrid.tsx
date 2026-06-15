"use client";
import { useMemo } from "react";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";
import { orderedPeriodTokens } from "@/lib/schedule/periods";
import { TimetableCell } from "./TimetableCell";
import { cn } from "@/lib/utils";

const WEEK = [1, 2, 3, 4, 5]; // Mon–Fri baseline; weekend days added only when present
const DAY_LABEL: Record<number, string> = { 0: "日", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六" };

export function WeeklyGrid() {
  const { periods, byId } = useTermCourses();
  const placed = useDraftStore((s) => s.placed);
  const viewMode = useUiStore((s) => s.viewMode);
  const selectedDay = useUiStore((s) => s.selectedDay);
  // Weekend columns are driven by the user's *placed* courses, not the catalog:
  // every term's catalog always carries Saturday courses, so scanning it would pin
  // 週六 on forever. 週一~週五 always; 週六/週日 appear only once the user places a
  // course on that day (週日 always sorts last).
  const weekDays = useMemo(() => {
    const days = new Set<number>(WEEK); // 1..5 baseline
    for (const p of placed) for (const m of byId(p.offering_id)?.meetings ?? []) {
      if (m.day === 0 || m.day === 6) days.add(m.day);
    }
    return [...days].sort((a, b) => (a === 0 ? 7 : a) - (b === 0 ? 7 : b)); // 日 (0) sorts last
  }, [placed, byId]);
  const DAYS = viewMode === "day" ? [selectedDay] : weekDays;
  const tokens = useMemo(() => (periods ? orderedPeriodTokens(periods) : []), [periods]);
  const startOf = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of periods?.periods ?? []) m.set(p.token, p.start_hm);
    return m;
  }, [periods]);
  if (!periods) return null;

  return (
    <div
      className="grid h-full gap-1"
      style={{
        gridTemplateColumns: `3rem repeat(${DAYS.length}, minmax(0,1fr))`,
        gridTemplateRows: `2rem repeat(${tokens.length}, minmax(2.6rem, 1fr))`,
      }}
    >
      <div />
      {DAYS.map((d) => (
        <div key={d} className="flex items-center justify-center text-[13px] font-semibold text-[var(--ink-soft)]">
          週{DAY_LABEL[d]}
        </div>
      ))}

      {tokens.map((tok) => {
        const lunch = tok === "N";
        const evening = ["A", "B", "C", "D"].includes(tok);
        return (
          <FragmentRow key={tok} token={tok} start={startOf.get(tok)} days={DAYS} muted={lunch || evening} />
        );
      })}
    </div>
  );
}

function FragmentRow({ token, start, days, muted }: { token: string; start?: string; days: number[]; muted: boolean }) {
  return (
    <>
      <div className={cn("flex flex-col items-center justify-center leading-none", muted && "opacity-70")}>
        <span className="text-xs font-semibold text-[var(--ink-soft)]">{token}</span>
        {start && <span className="mt-0.5 text-[9px] tabular-nums text-zinc-400">{start}</span>}
      </div>
      {days.map((d) => <TimetableCell key={`${d}-${token}`} day={d} period={token} />)}
    </>
  );
}
