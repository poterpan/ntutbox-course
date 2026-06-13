"use client";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useDraftStore } from "@/store/draft-store";
import { Button } from "@/components/ui/button";

export function FavoritesList() {
  const { byId } = useTermCourses();
  const { favorites, placed, place, toggleFavorite } = useDraftStore();
  if (favorites.length === 0)
    return <p className="p-3 text-xs text-zinc-400">尚無收藏（在課程庫按 ★）</p>;

  return (
    <div className="space-y-1 p-3">
      {favorites.map((id) => {
        const c = byId(id);
        if (!c) return null;
        const isPlaced = placed.some((p) => p.offering_id === id);
        return (
          <div key={id} className="flex items-center gap-2 rounded bg-white/60 px-2 py-1 text-xs">
            <span className="flex-1 truncate">{c.name.zh}</span>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 px-1 text-amber-500"
              aria-label="取消收藏"
              onClick={() => toggleFavorite(id)}
            >
              ★
            </Button>
            <Button
              size="sm"
              className="h-6 px-2"
              aria-label="排入"
              disabled={isPlaced}
              onClick={() => place(id)}
            >
              ＋
            </Button>
          </div>
        );
      })}
    </div>
  );
}
