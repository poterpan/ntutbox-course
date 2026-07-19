"use client";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useMprograms } from "@/lib/planner/use-mprograms";
import { getProgramOidSet } from "@/lib/planner/mprogram-index";
import { useDraftStore } from "@/store/draft-store";
import { useTermStore } from "@/store/term-store";
import { useUiStore } from "@/store/ui-store";
import { CourseListItem } from "./CourseListItem";

export function FavoritesList() {
  const { byId } = useTermCourses();
  const favorites = useDraftStore((s) => s.favorites);
  // 收藏列共用 CourseListItem → 同源 mprogram 聯集集合，微學程 badge 與課程庫一致。
  const storeTermKey = useTermStore((s) => s.termKey);
  const selectedTerm = useUiStore((s) => s.selectedTerm);
  const { data: mprogDir } = useMprograms(storeTermKey ?? selectedTerm);
  const mprogramOids = getProgramOidSet(mprogDir);

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
        return c ? <CourseListItem key={id} course={c} mprogramOids={mprogramOids} /> : null;
      })}
    </div>
  );
}
