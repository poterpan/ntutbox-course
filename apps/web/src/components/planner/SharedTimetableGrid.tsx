"use client";
import { useMemo } from "react";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { occupantsForSlot } from "@/lib/planner/resolve";
import { orderedPeriodTokens } from "@/lib/schedule/periods";
import type { PlacedCourse } from "@/store/draft-store";
import type { CourseOffering } from "@/lib/data/types";
import { cn } from "@/lib/utils";

const WEEK = [1, 2, 3, 4, 5];
const DAY_LABEL: Record<number, string> = { 0: "日", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六" };

/** Read-only weekly grid rendered from an arbitrary placed list (a shared plan) —
 * NOT the draft store, and with no slot interactions. Reuses the same occupancy
 * logic (occupantsForSlot) as the interactive grid so it can't drift. */
export function SharedTimetableGrid({ placed }: { placed: PlacedCourse[] }) {
  const { periods, byId } = useTermCourses();

  const weekDays = useMemo(() => {
    const days = new Set<number>(WEEK);
    for (const p of placed) for (const m of byId(p.offering_id)?.meetings ?? []) {
      if (m.day === 0 || m.day === 6) days.add(m.day);
    }
    return [...days].sort((a, b) => (a === 0 ? 7 : a) - (b === 0 ? 7 : b));
  }, [placed, byId]);

  const tokens = useMemo(() => (periods ? orderedPeriodTokens(periods) : []), [periods]);
  const startOf = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of periods?.periods ?? []) m.set(p.token, p.start_hm);
    return m;
  }, [periods]);

  if (!periods) return null;

  return (
    <div
      className="grid gap-1"
      style={{
        gridTemplateColumns: `2.5rem repeat(${weekDays.length}, minmax(0,1fr))`,
        gridAutoRows: "minmax(2.4rem, 1fr)",
      }}
    >
      <div />
      {weekDays.map((d) => (
        <div key={d} className="flex items-center justify-center text-[12px] font-semibold text-[var(--ink-soft)]">
          週{DAY_LABEL[d]}
        </div>
      ))}

      {tokens.map((tok) => (
        <ReadonlyRow key={tok} token={tok} start={startOf.get(tok)} days={weekDays} placed={placed} byId={byId} />
      ))}
    </div>
  );
}

function ReadonlyRow({
  token,
  start,
  days,
  placed,
  byId,
}: {
  token: string;
  start?: string;
  days: number[];
  placed: PlacedCourse[];
  byId: (id: string) => CourseOffering | undefined;
}) {
  return (
    <>
      <div className="flex flex-col items-center justify-center leading-none">
        <span className="text-[11px] font-semibold text-[var(--ink-soft)]">{token}</span>
        {start && <span className="mt-0.5 text-[8px] tabular-nums text-[var(--ink-faint)]">{start}</span>}
      </div>
      {days.map((d) => {
        const ids = occupantsForSlot(placed, byId, d, token);
        const conflicted = ids.length > 1;
        const first = ids[0] ? byId(ids[0]) : undefined;
        return (
          <div
            key={`${d}-${token}`}
            className={cn(
              "overflow-hidden rounded-md p-1 text-[10px] leading-tight",
              ids.length === 0 && "bg-white/30 ring-1 ring-inset ring-black/[0.06]",
              ids.length === 1 && "bg-gradient-to-br from-sky-400/90 to-blue-500/90 text-white",
              conflicted && "bg-gradient-to-br from-amber-400/90 to-orange-500/90 text-white ring-1 ring-orange-400",
            )}
          >
            {first && (
              <span className="line-clamp-2 font-semibold">
                {first.name.zh}
                {conflicted ? ` +${ids.length - 1}` : ""}
              </span>
            )}
          </div>
        );
      })}
    </>
  );
}
