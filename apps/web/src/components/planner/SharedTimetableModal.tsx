"use client";
import { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AccentButton } from "@/components/ui/accent-button";
import { SharedTimetableGrid } from "./SharedTimetableGrid";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useTermStore } from "@/store/term-store";
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
  const { byId } = useTermCourses();
  const status = useTermStore((s) => s.status);
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
  // 依 term 載入狀態判斷 loading —— term 不存在時 status 會變 error，才不會卡在「載入中」。
  const loading = status === "idle" || status === "loading";
  const dropped = (sharedPlan?.offeringIds.length ?? 0) - validIds.length;
  // 無固定時段的分享課（不會出現在上方週課表格線，需另外提示）。
  const noTimeShared = useMemo(
    () => validIds.map((id) => byId(id)).filter((c): c is NonNullable<typeof c> => !!c && (c.meetings ?? []).length === 0),
    [validIds, byId],
  );

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
            {noTimeShared.length > 0 && <span>・無固定時段 {noTimeShared.length}</span>}
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
              {noTimeShared.length > 0 && (
                <div className="rounded-lg bg-black/[0.03] p-2.5">
                  <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--ink-soft)]">
                    無固定時段（{noTimeShared.length}）· 不顯示在上方格線
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {noTimeShared.map((c) => (
                      <span key={c.offering_id} className="rounded-full bg-white/85 px-2.5 py-1 text-xs text-[var(--ink)] ring-1 ring-black/10">
                        {c.name.zh}
                      </span>
                    ))}
                  </div>
                </div>
              )}
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
              <div className="space-y-2">
                <p className="text-xs leading-relaxed text-[var(--ink-soft)]">
                  你該學期已有排課：<b className="text-[var(--ink)]">合併</b>＝保留現有再加入分享的課；
                  <b className="text-[var(--ink)]">取代</b>＝<span className="text-orange-600">清空</span>目前排課後改用分享課表。
                </p>
                <div className="flex items-center gap-2">
                  <AccentButton onClick={() => doImport("merge")}>合併</AccentButton>
                  <AccentButton tone="soft" onClick={() => doImport("replace")}>取代</AccentButton>
                  <button type="button" className="ml-auto rounded-lg px-2 py-1 text-xs text-[var(--ink-soft)] hover:bg-black/5" onClick={() => setChoosing(false)}>
                    取消
                  </button>
                </div>
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
