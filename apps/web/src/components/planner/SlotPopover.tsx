"use client";
import { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";
import { applyFilters } from "@/lib/filters/apply";
import { EMPTY_FILTER } from "@/lib/filters/types";
import { search } from "@/lib/search/search";
import { buildIndex } from "@/lib/search/build-index";

export function SlotPopover() {
  const { courses, byId } = useTermCourses();
  const { placed, place, unplace, setPriority } = useDraftStore();
  const { activeSlot, openSlot } = useUiStore();
  const [q, setQ] = useState("");

  const placedHere = useMemo(() => {
    if (!activeSlot) return [];
    return placed
      .filter((p) => byId(p.offering_id)?.meetings.some((m) => m.day === activeSlot.day && m.periods.includes(activeSlot.period)))
      .sort((a, b) => a.priority - b.priority);
  }, [placed, byId, activeSlot]);

  const addable = useMemo(() => {
    if (!activeSlot) return [];
    const inSlot = applyFilters(courses, { ...EMPTY_FILTER, weekdays: [activeSlot.day], periods: [activeSlot.period] });
    const placedIds = new Set(placed.map((p) => p.offering_id));
    const ids = new Set(search(buildIndex(inSlot), q).map((d) => d.offeringId));
    return inSlot.filter((c) => ids.has(c.offering_id) && !placedIds.has(c.offering_id));
  }, [courses, activeSlot, placed, q]);

  if (!activeSlot) return null;

  const swap = (id: string, dir: -1 | 1) => {
    const idx = placedHere.findIndex((p) => p.offering_id === id);
    const other = placedHere[idx + dir];
    if (!other) return;
    const cur = placedHere[idx];
    setPriority(cur.offering_id, other.priority);
    setPriority(other.offering_id, cur.priority);
  };

  return (
    <Dialog open onOpenChange={(o) => { if (!o) openSlot(null); }}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>星期{activeSlot.day} · 第 {activeSlot.period} 節</DialogTitle></DialogHeader>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜尋此時段課程…" aria-label="搜尋此時段" />

        {placedHere.length > 0 && (
          <div className="space-y-1">
            <div className="text-[10px] uppercase text-zinc-400">已排入此格（志願序）</div>
            {placedHere.map((p, i) => {
              const c = byId(p.offering_id);
              return (
                <div key={p.offering_id} className="flex items-center gap-2 rounded bg-orange-50 px-2 py-1 text-xs">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-orange-500 text-[10px] text-white">{i + 1}</span>
                  <span className="flex-1 truncate">{c?.name.zh}</span>
                  <Button size="sm" variant="ghost" className="h-6 px-1" aria-label={`${c?.name.zh} 上移`} disabled={i === 0} onClick={() => swap(p.offering_id, -1)}>↑</Button>
                  <Button size="sm" variant="ghost" className="h-6 px-1" aria-label={`${c?.name.zh} 下移`} disabled={i === placedHere.length - 1} onClick={() => swap(p.offering_id, 1)}>↓</Button>
                  <Button size="sm" variant="ghost" className="h-6 px-1 text-red-500" aria-label={`移除 ${c?.name.zh}`} onClick={() => unplace(p.offering_id)}>✕</Button>
                </div>
              );
            })}
          </div>
        )}

        <div className="space-y-1">
          <div className="text-[10px] uppercase text-zinc-400">此時段其他可加入</div>
          {addable.map((c) => (
            <div key={c.offering_id} className="flex items-center gap-2 rounded bg-white px-2 py-1 text-xs">
              <span className="flex-1 truncate">{c.name.zh} <span className="text-[10px] text-zinc-400">{c.credits ?? "?"}學分</span></span>
              <Button size="sm" className="h-6 px-2" aria-label={`排入 ${c.name.zh}`} onClick={() => place(c.offering_id)}>＋</Button>
            </div>
          ))}
          {addable.length === 0 && <div className="text-xs text-zinc-400">無其他符合課程</div>}
        </div>
      </DialogContent>
    </Dialog>
  );
}
