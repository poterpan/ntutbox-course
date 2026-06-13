"use client";
import type { CourseOffering } from "@/lib/data/types";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";
import { cn } from "@/lib/utils";

export function CourseListItem({ course }: { course: CourseOffering }) {
  const { favorites, placed, place, toggleFavorite } = useDraftStore();
  const openDetail = useUiStore((s) => s.openDetail);
  const isFav = favorites.includes(course.offering_id);
  const isPlaced = placed.some((p) => p.offering_id === course.offering_id);
  const teachers = (course.teachers ?? []).map((t) => t.name).join("、") || "—";

  return (
    <div className="group mb-1.5 flex items-center gap-2 rounded-xl bg-white/55 px-3 py-2 ring-1 ring-black/[0.04] transition-colors hover:bg-white/85">
      <button type="button" className="min-w-0 flex-1 text-left" onClick={() => openDetail(course.offering_id)}>
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[13px] font-semibold text-[var(--ink)]">{course.name.zh}</span>
          <span className="shrink-0 rounded-md bg-[var(--accent)]/10 px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-[var(--accent)]">
            {course.credits ?? "?"} 學分
          </span>
        </div>
        <div className="mt-0.5 truncate text-[11px] text-[var(--ink-soft)]">
          {teachers} · {course.offering_id}
        </div>
      </button>
      <button
        type="button"
        aria-label="收藏"
        onClick={() => toggleFavorite(course.offering_id)}
        className={cn(
          "flex size-7 shrink-0 items-center justify-center rounded-lg text-base transition-colors",
          isFav ? "text-amber-500" : "text-zinc-300 hover:bg-black/5 hover:text-amber-400",
        )}
      >
        {isFav ? "★" : "☆"}
      </button>
      <button
        type="button"
        aria-label="排入"
        disabled={isPlaced}
        onClick={() => place(course.offering_id)}
        className={cn(
          "flex h-7 shrink-0 items-center justify-center rounded-lg px-2.5 text-xs font-medium transition-colors",
          isPlaced
            ? "cursor-default bg-black/5 text-zinc-400"
            : "bg-[var(--accent)] text-white hover:brightness-110",
        )}
      >
        {isPlaced ? "已排" : "＋ 排入"}
      </button>
    </div>
  );
}
