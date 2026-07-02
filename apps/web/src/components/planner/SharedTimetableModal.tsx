"use client";
import { useMemo, useState } from "react";
import { ChevronLeftIcon } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AccentButton } from "@/components/ui/accent-button";
import { SharedTimetableGrid } from "./SharedTimetableGrid";
import { CourseDetailContent } from "./CourseDetailContent";
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
  const draftCount = useDraftStore((s) => s.placed.length);
  const [choosing, setChoosing] = useState(false);
  // 就地詳情：非 null 時，彈窗內容原地切成該課詳情（不開新 dialog）。
  const [detailId, setDetailId] = useState<string | null>(null);

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
    <Dialog open={open} onOpenChange={(o) => { if (!o) { setOpen(false); setChoosing(false); setDetailId(null); } }}>
      <DialogContent className="flex h-[85vh] w-[94vw] max-w-[94vw] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        {detailId ? (
          <>
            <DialogTitle className="sr-only">課程詳情</DialogTitle>
            <CourseDetailContent
              offeringId={detailId}
              onAfterPlace={() => setDetailId(null)}
              headerLeading={
                <button
                  type="button"
                  onClick={() => setDetailId(null)}
                  aria-label="返回課表"
                  className="-ml-2 flex items-center gap-0.5 rounded-lg py-1 pl-1 pr-2 text-sm font-semibold text-[var(--accent)] transition-colors hover:bg-[var(--accent)]/10"
                >
                  <ChevronLeftIcon className="size-4" aria-hidden />
                  課表
                </button>
              }
            />
          </>
        ) : (
          <>
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
              <SharedTimetableGrid placed={placed} onCourseClick={setDetailId} />
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
                    <li key={id}>
                    <button
                      type="button"
                      onClick={() => setDetailId(id)}
                      className="flex w-full items-center gap-2 rounded-lg bg-black/[0.02] px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-black/[0.05]"
                    >
                      <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)]/12 text-[10px] font-bold tabular-nums text-[var(--accent-ink)]">
                        {i + 1}
                      </span>
                      <span className="min-w-0 flex-1 truncate font-medium text-[var(--ink)]">{c?.name.zh}</span>
                      <span className="shrink-0 tabular-nums text-[var(--ink-soft)]">{c?.credits ?? "?"} 學分</span>
                    </button>
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
              <div className="space-y-2.5">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="text-sm font-bold text-[var(--ink)]">要怎麼加入這份課表？</p>
                  <span className="shrink-0 text-xs font-semibold text-[var(--ink-faint)] tabular-nums">你目前已有 {draftCount} 門</span>
                </div>
                {/* 兩張全寬選項卡：整塊可點、各帶說明；合併=建議、取代=橘色警示。手機直疊、桌機並排。 */}
                <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                  <button
                    type="button"
                    onClick={() => doImport("merge")}
                    className="flex items-start gap-3 rounded-xl border border-[var(--accent)]/40 bg-[var(--accent)]/10 p-3 text-left transition-colors hover:bg-[var(--accent)]/15"
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent)] text-lg font-bold leading-none text-white">＋</span>
                    <span className="min-w-0">
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-bold text-[var(--ink)]">合併到目前規劃</span>
                        <span className="shrink-0 text-[11px] font-bold text-[var(--accent-ink)]">建議</span>
                      </span>
                      <span className="mt-0.5 block text-xs leading-relaxed text-[var(--ink-soft)]">保留你原本排好的課，只加入分享課表中尚未排入的課。</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => doImport("replace")}
                    className="flex items-start gap-3 rounded-xl border border-orange-600/25 bg-orange-600/[0.06] p-3 text-left transition-colors hover:bg-orange-600/10"
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-orange-600/10 text-lg font-bold leading-none text-orange-600">↻</span>
                    <span className="min-w-0">
                      <span className="block font-bold text-[var(--ink)]">取代目前規劃</span>
                      <span className="mt-0.5 block text-xs leading-relaxed text-[var(--ink-soft)]">
                        <b className="font-bold text-orange-600">會清空目前排課</b>，再套用這份分享課表。
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setChoosing(false)}
                    className="rounded-xl px-4 py-2 text-sm font-semibold text-[var(--ink-soft)] transition-colors hover:bg-black/5 sm:h-full"
                  >
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
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
