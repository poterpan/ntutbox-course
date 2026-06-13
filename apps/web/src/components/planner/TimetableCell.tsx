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
  const conflicted = ids.length > 1;

  return (
    <button
      type="button"
      data-testid={conflicted ? "conflict-cell" : undefined}
      onClick={() => openSlot({ day, period })}
      className={cn("h-full w-full rounded-md p-1 text-left text-[11px] leading-tight transition-colors",
        ids.length === 0 && "bg-white/40 hover:bg-white/70",
        ids.length === 1 && "bg-sky-200/70 text-sky-900 hover:bg-sky-200",
        conflicted && "bg-orange-300/80 text-orange-950 ring-2 ring-orange-500 hover:bg-orange-300")}
      aria-label={`星期${day} 第${period}節${conflicted ? `（${ids.length} 個志願）` : ""}`}
    >
      {ids.length === 1 && <span className="font-semibold">{byId(ids[0])?.name.zh}</span>}
      {conflicted && (
        <div className="flex h-full flex-col gap-0.5">
          {/* first preference prominent */}
          <span className="font-bold">{byId(ids[0])?.name.zh}</span>
          {/* later preferences as small names (desktop). Mobile hides via CSS (+N badge). */}
          <div className="hidden flex-col sm:flex">
            {ids.slice(1).map((id, i) => (
              <span key={id} className="text-[9px] text-orange-900/80">
                <span>{i + 2}. </span>
                <span>{byId(id)?.name.zh}</span>
              </span>
            ))}
          </div>
          {/* mobile fallback: +N badge */}
          <span className="mt-auto self-end rounded bg-orange-600 px-1 text-[9px] font-semibold text-white sm:hidden">
            +{ids.length - 1}
          </span>
        </div>
      )}
    </button>
  );
}
