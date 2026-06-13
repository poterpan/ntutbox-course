"use client";
import type { CourseOffering } from "@/lib/data/types";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function CourseListItem({ course }: { course: CourseOffering }) {
  const { favorites, placed, place, toggleFavorite } = useDraftStore();
  const openDetail = useUiStore((s) => s.openDetail);
  const isFav = favorites.includes(course.offering_id);
  const isPlaced = placed.some((p) => p.offering_id === course.offering_id);

  return (
    <div className="flex items-center gap-2 rounded-lg bg-white/60 px-2 py-1.5 text-xs">
      <button type="button" className="min-w-0 flex-1 text-left" onClick={() => openDetail(course.offering_id)}>
        <div className="truncate font-semibold text-zinc-800">{course.name.zh}</div>
        <div className="truncate text-[10px] text-zinc-500">
          {course.credits ?? "?"}學分 · {(course.teachers ?? []).map((t) => t.name).join("、") || "—"} · {course.offering_id}
        </div>
      </button>
      <Button size="sm" variant="ghost" aria-label="收藏"
        className={cn("h-7 px-2", isFav && "text-amber-500")} onClick={() => toggleFavorite(course.offering_id)}>★</Button>
      <Button size="sm" variant={isPlaced ? "secondary" : "default"} aria-label="排入"
        className="h-7 px-2" disabled={isPlaced} onClick={() => place(course.offering_id)}>{isPlaced ? "已排" : "＋"}</Button>
    </div>
  );
}
