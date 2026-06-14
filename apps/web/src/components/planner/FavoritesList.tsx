"use client";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useDraftStore } from "@/store/draft-store";
import { CourseListItem } from "./CourseListItem";

export function FavoritesList() {
  const { byId } = useTermCourses();
  const favorites = useDraftStore((s) => s.favorites);

  if (favorites.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-1 p-6 text-center">
        <span className="text-2xl">☆</span>
        <p className="text-sm text-[var(--ink-soft)]">尚無收藏</p>
        <p className="text-xs text-[var(--ink-faint)]">在課程庫點任一課程的 ★ 加入帶選清單</p>
      </div>
    );
  }

  // Reuse the polished course card (★ here = unfavorite; ＋/已排 + tap→detail work the same).
  return (
    <div className="space-y-1.5 p-4 pt-3">
      {favorites.map((id) => {
        const c = byId(id);
        return c ? <CourseListItem key={id} course={c} /> : null;
      })}
    </div>
  );
}
