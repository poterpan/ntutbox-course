"use client";
import { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useTouchScrollFocus } from "@/lib/planner/use-touch-scroll-focus";
import { useSearchIndex } from "@/lib/planner/use-search-index";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";
import { useIdentityStore } from "@/store/identity-store";
import { applyFilters } from "@/lib/filters/apply";
import { EMPTY_FILTER } from "@/lib/filters/types";
import { search } from "@/lib/search/search";
import { resolveMatric, GROUP_LABEL } from "@/lib/planner/matric";
import { cn } from "@/lib/utils";

const DAY = ["日", "一", "二", "三", "四", "五", "六"];

export function SlotPopover() {
  const { courses, byId } = useTermCourses();
  const index = useSearchIndex();
  const { placed, place, unplace, setPriority } = useDraftStore();
  const { activeSlot, openSlot, openDetail } = useUiStore();
  const userGroup = useIdentityStore((s) => s.matricGroup);
  const [q, setQ] = useState("");
  const [showAllMatric, setShowAllMatric] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  // Avoid auto-focusing the search input on touch so the course list scrolls on first drag.
  const { scrollRef, initialFocus } = useTouchScrollFocus();

  const placedHere = useMemo(() => {
    if (!activeSlot) return [];
    return placed
      .filter((p) =>
        (byId(p.offering_id)?.meetings ?? []).some(
          (m) => m.day === activeSlot.day && (m.periods as string[]).includes(activeSlot.period),
        ),
      )
      .sort((a, b) => a.priority - b.priority);
  }, [placed, byId, activeSlot]);

  const manage = placedHere.length > 0;

  const candidates = useMemo(() => {
    if (!activeSlot || manage) return [];
    const inSlot = applyFilters(courses, { ...EMPTY_FILTER, weekdays: [activeSlot.day], periods: [activeSlot.period] });
    const placedIds = new Set(placed.map((p) => p.offering_id));
    const inSlotIds = new Set(inSlot.map((c) => c.offering_id));
    const ranked = q.trim() ? search(index, q).map((d) => d.offeringId).filter((id) => inSlotIds.has(id)) : inSlot.map((c) => c.offering_id);
    return ranked.filter((id) => !placedIds.has(id)).map((id) => byId(id)!).filter(Boolean);
  }, [courses, index, activeSlot, placed, q, manage, byId]);

  // 學制感知：選了學制時，預設只顯本學制的課；「顯示其他學制」開關可展開。
  const { addable, hiddenByMatric } = useMemo(() => {
    if (userGroup == null || showAllMatric) return { addable: candidates.slice(0, 100), hiddenByMatric: 0 };
    const own = candidates.filter((c) => { const d = resolveMatric(c); return !d || d.group === userGroup; });
    return { addable: own.slice(0, 100), hiddenByMatric: candidates.length - own.length };
  }, [candidates, userGroup, showAllMatric]);

  if (!activeSlot) return null;

  const swap = (id: string, dir: -1 | 1) => {
    const idx = placedHere.findIndex((p) => p.offering_id === id);
    const other = placedHere[idx + dir];
    if (!other) return;
    const cur = placedHere[idx];
    setPriority(cur.offering_id, other.priority);
    setPriority(other.offering_id, cur.priority);
  };

  // Reassign the group's existing priority values to a new visual order
  // (keeps relative order vs. courses outside this slot).
  const applyOrder = (orderedIds: string[]) => {
    const prios = placedHere.map((p) => p.priority).slice().sort((a, b) => a - b);
    orderedIds.forEach((id, i) => setPriority(id, prios[i]));
  };
  const dropOn = (targetId: string) => {
    if (!dragId || dragId === targetId) return setDragId(null);
    const ids = placedHere.map((p) => p.offering_id);
    const from = ids.indexOf(dragId);
    const to = ids.indexOf(targetId);
    if (from < 0 || to < 0) return setDragId(null);
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    applyOrder(ids);
    setDragId(null);
  };

  const openCourse = (id: string) => { openSlot(null); openDetail(id); };

  return (
    <Dialog open onOpenChange={(o) => { if (!o) openSlot(null); }}>
      <DialogContent
        initialFocus={initialFocus}
        className="flex max-h-[80vh] w-[92vw] max-w-md flex-col gap-0 overflow-hidden p-0"
      >
        <DialogHeader className="border-b border-black/5 px-5 py-3">
          <DialogTitle>週{DAY[activeSlot.day]} · 第 {activeSlot.period} 節</DialogTitle>
        </DialogHeader>

        {manage ? (
          <>
            <div ref={scrollRef} tabIndex={-1} className="thin-scroll min-h-0 flex-1 space-y-1.5 overflow-y-auto overscroll-contain p-3 outline-none [touch-action:pan-y]">
              <div className="px-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--ink-soft)]">
                已排入此格{placedHere.length > 1 ? "（拖／按鈕調整志願序）" : ""}
              </div>
              {placedHere.map((p, i) => {
                const c = byId(p.offering_id);
                const multi = placedHere.length > 1;
                return (
                  <div
                    key={p.offering_id}
                    draggable={multi}
                    onDragStart={() => setDragId(p.offering_id)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => dropOn(p.offering_id)}
                    onDragEnd={() => setDragId(null)}
                    className={cn(
                      "flex items-center gap-1.5 rounded-xl bg-orange-50 px-2 py-1.5 text-xs ring-1 ring-orange-200 transition-opacity",
                      dragId === p.offering_id && "opacity-40",
                    )}
                  >
                    {multi && (
                      <span className="shrink-0 cursor-grab select-none text-sm text-orange-400 active:cursor-grabbing" aria-hidden>⠿</span>
                    )}
                    <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-orange-500 text-[10px] font-bold text-white">{i + 1}</span>
                    <button type="button" className="min-w-0 flex-1 truncate text-left font-medium hover:underline" onClick={() => openCourse(p.offering_id)}>
                      {c?.name.zh}
                    </button>
                    {multi && (
                      <>
                        <button type="button" className="flex size-6 items-center justify-center rounded-md text-[var(--ink-soft)] hover:bg-black/5 disabled:opacity-30" aria-label={`${c?.name.zh} 上移`} disabled={i === 0} onClick={() => swap(p.offering_id, -1)}>↑</button>
                        <button type="button" className="flex size-6 items-center justify-center rounded-md text-[var(--ink-soft)] hover:bg-black/5 disabled:opacity-30" aria-label={`${c?.name.zh} 下移`} disabled={i === placedHere.length - 1} onClick={() => swap(p.offering_id, 1)}>↓</button>
                      </>
                    )}
                    <button type="button" className="flex h-6 shrink-0 items-center rounded-md px-2 text-[11px] font-medium text-red-500 hover:bg-red-100" aria-label={`退選 ${c?.name.zh}`} onClick={() => unplace(p.offering_id)}>退選</button>
                  </div>
                );
              })}
            </div>
            <p className="border-t border-black/5 px-4 py-2.5 text-[11px] text-[var(--ink-soft)]">
              要加入更多課程？在右側「課程庫」搜尋後按「排入」。
            </p>
          </>
        ) : (
          <>
            <div className="border-b border-black/5 p-3">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="搜尋此時段課程…"
                aria-label="搜尋此時段"
                className="w-full rounded-lg bg-black/[0.04] px-3 py-2 text-sm outline-none ring-1 ring-black/5 placeholder:text-zinc-400 focus:ring-[var(--accent)]/40"
              />
            </div>
            {userGroup != null && (
              <button
                type="button"
                onClick={() => setShowAllMatric((v) => !v)}
                className="flex w-full items-center justify-between border-b border-black/5 px-4 py-2 text-[11px] text-[var(--ink-soft)] transition-colors hover:bg-black/[0.03]"
              >
                <span>{showAllMatric ? "顯示所有學制" : `只顯示〔${GROUP_LABEL[userGroup]}〕`}</span>
                <span className="font-medium text-[var(--accent-ink)]">
                  {showAllMatric ? "只看本學制" : hiddenByMatric > 0 ? `顯示其他學制 +${hiddenByMatric}` : "顯示其他學制"}
                </span>
              </button>
            )}
            <div ref={scrollRef} tabIndex={-1} className="thin-scroll min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain p-3 outline-none [touch-action:pan-y]">
              {addable.length === 0 && <p className="py-6 text-center text-xs text-[var(--ink-soft)]">此時段沒有可加入的課程</p>}
              {addable.map((c) => (
                <div key={c.offering_id} className="flex items-center gap-2 rounded-xl bg-white px-2.5 py-1.5 text-xs ring-1 ring-black/5">
                  <button type="button" className="min-w-0 flex-1 text-left hover:underline" onClick={() => openCourse(c.offering_id)}>
                    <span className="font-medium">{c.name.zh}</span>
                    <span className="ml-1.5 text-[10px] text-[var(--ink-soft)]">{c.credits ?? "?"}學分 · {(c.teachers ?? []).map((t) => t.name).join("、") || "—"}</span>
                  </button>
                  <button type="button" className="flex h-7 shrink-0 items-center rounded-lg bg-[var(--accent)] px-3 text-[11px] font-semibold text-white hover:brightness-110" aria-label={`排入 ${c.name.zh}`} onClick={() => place(c.offering_id)}>＋ 排入</button>
                </div>
              ))}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
