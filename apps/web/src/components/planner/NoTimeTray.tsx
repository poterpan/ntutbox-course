"use client";
import { useMemo } from "react";
import { useDraftStore } from "@/store/draft-store";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useUiStore } from "@/store/ui-store";

/** Unobtrusive tray under the timetable for placed courses that have no time slot
 *  (實務專題 / 校外實習 / 論文 …). They count toward credits but can't sit in a cell. */
export function NoTimeTray() {
  const placed = useDraftStore((s) => s.placed);
  const unplace = useDraftStore((s) => s.unplace);
  const { byId } = useTermCourses();
  const openDetail = useUiStore((s) => s.openDetail);

  const noTime = useMemo(
    () =>
      placed
        .map((p) => byId(p.offering_id))
        .filter((c): c is NonNullable<typeof c> => !!c && (c.meetings ?? []).length === 0),
    [placed, byId],
  );

  if (noTime.length === 0) return null;

  return (
    <div className="mt-2 shrink-0 border-t border-black/5 pt-2" data-testid="no-time-tray">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--ink-soft)]">
        無固定時段（{noTime.length}）
      </div>
      <div className="flex flex-wrap gap-1.5">
        {noTime.map((c) => (
          <span
            key={c.offering_id}
            className="flex items-center gap-1.5 rounded-full bg-white/85 py-1 pl-3 pr-1.5 text-xs ring-1 ring-black/10"
          >
            <button
              type="button"
              className="font-medium text-[var(--ink)] hover:underline"
              onClick={() => openDetail(c.offering_id)}
            >
              {c.name.zh}
            </button>
            <span className="text-[10px] tabular-nums text-[var(--ink-soft)]">{c.credits ?? "?"}學分</span>
            <button
              type="button"
              aria-label={`退選 ${c.name.zh}`}
              className="flex size-4 items-center justify-center rounded-full text-[var(--ink-soft)] transition-colors hover:bg-red-100 hover:text-red-500"
              onClick={() => unplace(c.offering_id)}
            >
              ✕
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}
