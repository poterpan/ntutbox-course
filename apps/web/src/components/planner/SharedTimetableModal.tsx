"use client";
import { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AccentButton } from "@/components/ui/accent-button";
import { SharedTimetableGrid } from "./SharedTimetableGrid";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { creditSummary } from "@/lib/schedule/credits";
import { useDraftStore, type PlacedCourse } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";
import { useToast } from "@/components/ui/toast";

/** F-B: read-only overlay of a shared timetable. Renders from ui-store.sharedPlan
 * (NOT the draft) so it never pollutes the recipient's plan until they import. */
export function SharedTimetableModal() {
  const sharedPlan = useUiStore((s) => s.sharedPlan);
  const open = useUiStore((s) => s.sharedPlanOpen);
  const setOpen = useUiStore((s) => s.setSharedPlanOpen);
  const clearSharedPlan = useUiStore((s) => s.clearSharedPlan);
  const { courses, byId } = useTermCourses();
  const showToast = useToast((s) => s.show);
  const [choosing, setChoosing] = useState(false);

  // Valid (still-existing) shared offerings, in shared order (= 志願序).
  const validIds = useMemo(
    () => (sharedPlan?.offeringIds ?? []).filter((id) => byId(id)),
    [sharedPlan, byId],
  );
  const placed: PlacedCourse[] = useMemo(
    () => validIds.map((offering_id, i) => ({ offering_id, priority: i + 1 })),
    [validIds],
  );
  const summary = useMemo(() => creditSummary(placed, byId), [placed, byId]);
  const loading = courses.length === 0; // term catalog not loaded yet
  const dropped = (sharedPlan?.offeringIds.length ?? 0) - validIds.length;

  if (!sharedPlan) return null;

  function onImportClick() {
    if (useDraftStore.getState().placed.length > 0) setChoosing(true);
    else doImport("merge");
  }
  function doImport(mode: "merge" | "replace") {
    if (mode === "replace") {
      useDraftStore.setState({ placed: validIds.map((offering_id, i) => ({ offering_id, priority: i + 1 })) });
    } else {
      const place = useDraftStore.getState().place;
      validIds.forEach((id) => place(id)); // dedups + appends priority
    }
    setChoosing(false);
    clearSharedPlan();
    showToast(dropped > 0 ? `已匯入 ${validIds.length} 門（${dropped} 門已失效略過）` : "已複製到你的規劃");
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { setOpen(false); setChoosing(false); } }}>
      <DialogContent className="flex h-[85vh] w-[94vw] max-w-[94vw] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <DialogHeader className="border-b border-black/5 px-5 py-3">
          <DialogTitle className="text-lg font-bold">分享的課表</DialogTitle>
          <p className="mt-0.5 text-xs text-[var(--ink-soft)] tabular-nums">
            {sharedPlan.termKey} · {validIds.length} 門 · {summary.placedCredits} 學分
            {summary.conflictGroupCount > 0 && <span className="text-orange-600">・衝堂 {summary.conflictGroupCount}</span>}
          </p>
        </DialogHeader>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          {loading ? (
            <p className="py-10 text-center text-sm text-[var(--ink-soft)]">載入課表中…</p>
          ) : validIds.length === 0 ? (
            <p className="py-10 text-center text-sm text-[var(--ink-soft)]">此課表的課程多已更新或不存在。</p>
          ) : (
            <>
              <SharedTimetableGrid placed={placed} />
              <ul className="space-y-1">
                {validIds.map((id, i) => {
                  const c = byId(id);
                  return (
                    <li key={id} className="flex items-center gap-2 rounded-lg bg-black/[0.02] px-2.5 py-1.5 text-xs">
                      <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)]/12 text-[10px] font-bold tabular-nums text-[var(--accent-ink)]">
                        {i + 1}
                      </span>
                      <span className="min-w-0 flex-1 truncate font-medium text-[var(--ink)]">{c?.name.zh}</span>
                      <span className="shrink-0 tabular-nums text-[var(--ink-soft)]">{c?.credits ?? "?"} 學分</span>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>

        {!loading && validIds.length > 0 && (
          <div className="border-t border-black/5 px-5 py-3">
            {choosing ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--ink-soft)]">你該學期已有排課：</span>
                <AccentButton onClick={() => doImport("merge")}>合併</AccentButton>
                <AccentButton tone="soft" onClick={() => doImport("replace")}>取代</AccentButton>
                <button type="button" className="ml-auto rounded-lg px-2 py-1 text-xs text-[var(--ink-soft)] hover:bg-black/5" onClick={() => setChoosing(false)}>
                  取消
                </button>
              </div>
            ) : (
              <AccentButton size="lg" className="w-full" onClick={onImportClick}>
                ＋ 複製到我的規劃
              </AccentButton>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
