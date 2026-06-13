"use client";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useScheduleView } from "@/lib/planner/use-schedule-view";
import { useUiStore } from "@/store/ui-store";
import { cn } from "@/lib/utils";

export function TimetableCell({ day, period }: { day: number; period: string }) {
  const { byId } = useTermCourses();
  const { occupants } = useScheduleView();
  const openSlot = useUiStore((s) => s.openSlot);
  const ids = occupants(day, period);

  return (
    <button
      type="button"
      onClick={() => openSlot({ day, period })}
      className={cn("h-full w-full rounded-md p-1 text-left text-[11px] leading-tight transition-colors",
        ids.length === 0 ? "bg-white/40 hover:bg-white/70" : "bg-sky-200/70 text-sky-900 hover:bg-sky-200")}
      aria-label={`星期${day} 第${period}節`}
    >
      {ids.length === 1 && (() => {
        const c = byId(ids[0]);
        return <span className="font-semibold">{c?.name.zh}</span>;
      })()}
    </button>
  );
}
