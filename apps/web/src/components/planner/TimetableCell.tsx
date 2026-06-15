"use client";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useScheduleView } from "@/lib/planner/use-schedule-view";
import { useUiStore } from "@/store/ui-store";
import { cn } from "@/lib/utils";

export function TimetableCell({ day, period }: { day: number; period: string }) {
  const { byId } = useTermCourses();
  const { occupants } = useScheduleView();
  const openSlot = useUiStore((s) => s.openSlot);
  const openDetail = useUiStore((s) => s.openDetail);
  const hoveredOfferingId = useUiStore((s) => s.hoveredOfferingId);
  const ids = occupants(day, period);
  const conflicted = ids.length > 1;
  const first = ids[0] ? byId(ids[0]) : undefined;
  const room = first?.classrooms?.[0]?.name;

  // Hover ghost (desktop): the course hovered in the library meets at this (day, period).
  // Touch is gated upstream (CourseListItem only sets hover for mouse pointers).
  const ghostHere = hoveredOfferingId != null &&
    (byId(hoveredOfferingId)?.meetings ?? []).some((m) => m.day === day && (m.periods as string[]).includes(period));
  // 衝堂預檢: this cell is already taken by a *placed* course that isn't the hovered one.
  const ghostConflict = ghostHere && ids.some((id) => id !== hoveredOfferingId);
  const ghostPreview = ghostHere && !ghostConflict;

  // empty → find courses for this time; single placed → its detail (退選); conflict → manage slot
  const onClick = () => {
    if (ids.length === 0) openSlot({ day, period });
    else if (ids.length === 1) openDetail(ids[0]);
    else openSlot({ day, period });
  };

  return (
    <button
      type="button"
      data-testid={conflicted ? "conflict-cell" : undefined}
      onClick={onClick}
      className={cn(
        "relative size-full overflow-hidden rounded-md p-1 text-left text-[11px] leading-tight transition-all",
        ids.length === 0 &&
          "bg-white/30 ring-1 ring-inset ring-black/[0.06] hover:bg-white/70 hover:ring-[var(--accent)]/30",
        ids.length === 1 &&
          "bg-gradient-to-br from-sky-400/90 to-blue-500/90 text-white shadow-sm hover:from-sky-400 hover:to-blue-500",
        conflicted &&
          "bg-gradient-to-br from-amber-400/90 to-orange-500/90 text-white shadow-sm ring-2 ring-orange-400 hover:brightness-105",
      )}
      aria-label={`星期${day} 第${period}節${conflicted ? `（${ids.length} 個志願）` : ""}`}
    >
      {ids.length === 1 && first && (
        <div className="flex h-full flex-col gap-0.5">
          <span className="line-clamp-2 font-semibold">{first.name.zh}</span>
          {room && <span className="mt-auto truncate text-[9px] text-white/80">{room}</span>}
        </div>
      )}

      {conflicted && (
        <div className="flex h-full flex-col gap-0.5">
          <span className="line-clamp-2 font-bold">{first?.name.zh}</span>
          <div className="hidden flex-col sm:flex">
            {ids.slice(1, 3).map((id, i) => (
              <span key={id} className="truncate text-[9px] text-white/85">
                <span>{i + 2}. </span>
                <span>{byId(id)?.name.zh}</span>
              </span>
            ))}
          </div>
          <span className="mt-auto self-start rounded bg-white/30 px-1 text-[9px] font-semibold sm:hidden">
            +{ids.length - 1}
          </span>
        </div>
      )}

      {/* Ghost preview overlay — dashed outline + low-opacity fill, distinct from
          placed (實心藍) / conflict (橘). Red when it would clash with a placed course. */}
      {ghostPreview && (
        <span
          data-testid="ghost-cell"
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-md border-2 border-dashed border-[var(--accent)] bg-[var(--accent)]/15"
        />
      )}
      {ghostConflict && (
        <span
          data-testid="ghost-conflict-cell"
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-md border-2 border-dashed border-red-500 bg-red-500/20"
        />
      )}
    </button>
  );
}
