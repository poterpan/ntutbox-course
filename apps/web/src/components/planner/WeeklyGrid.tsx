"use client";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { orderedPeriodTokens, periodLabel } from "@/lib/schedule/periods";
import { TimetableCell } from "./TimetableCell";

const DAYS = [1, 2, 3, 4, 5, 6];
const DAY_LABEL: Record<number, string> = { 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 0: "日" };

export function WeeklyGrid() {
  const { periods } = useTermCourses();
  if (!periods) return null;
  const tokens = orderedPeriodTokens(periods);

  return (
    <div className="grid h-full gap-1"
      style={{ gridTemplateColumns: `2rem repeat(${DAYS.length}, minmax(0,1fr))`, gridTemplateRows: `1.5rem repeat(${tokens.length}, minmax(2.5rem, 1fr))` }}>
      <div />
      {DAYS.map((d) => <div key={d} className="flex items-center justify-center text-xs font-medium text-zinc-500">{DAY_LABEL[d]}</div>)}
      {tokens.map((tok) => (
        <FragmentRow key={tok} token={tok} label={periodLabel(tok, periods)} days={DAYS} />
      ))}
    </div>
  );
}

function FragmentRow({ token, label, days }: { token: string; label: string; days: number[] }) {
  return (
    <>
      <div className="flex items-center justify-center text-xs text-zinc-400">{label}</div>
      {days.map((d) => <TimetableCell key={`${d}-${token}`} day={d} period={token} />)}
    </>
  );
}
