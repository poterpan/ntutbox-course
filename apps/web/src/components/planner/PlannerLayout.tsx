"use client";
import { useTermStore } from "@/store/term-store";
import { useUiStore } from "@/store/ui-store";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/glass/GlassPanel";
import { WeeklyGrid } from "./WeeklyGrid";
import { CourseLibrary } from "./CourseLibrary";
import { SlotPopover } from "./SlotPopover";
import { CourseDetailDrawer } from "./CourseDetailDrawer";
import { CreditSummary } from "./CreditSummary";
import { TermSwitcher } from "./TermSwitcher";
import { FavoritesList } from "./FavoritesList";

const fmtDate = (iso: string | null) => (iso ? iso.slice(0, 10) : "—");

export function PlannerLayout() {
  const status = useTermStore((s) => s.status);
  const error = useTermStore((s) => s.error);
  const catalogAt = useTermStore((s) => s.catalogCrawledAt());
  const enrollAt = useTermStore((s) => s.enrollmentObservedAt());
  const libraryOpen = useUiStore((s) => s.libraryOpen);
  const setLibraryOpen = useUiStore((s) => s.setLibraryOpen);
  const staleDropped = useUiStore((s) => s.staleDropped);
  const dismissStale = useUiStore((s) => s.dismissStale);

  return (
    <main className="flex h-dvh flex-col">
      <header className="flex items-center gap-3 px-4 pt-4 pb-2 sm:px-5">
        <h1 className="text-lg font-bold tracking-tight text-[var(--ink)]">
          北科盒子 <span className="text-[var(--accent)]">排課</span>
        </h1>
        <TermSwitcher />
        <div className="ml-auto hidden text-right text-[10px] leading-tight text-[var(--ink-soft)] sm:block">
          <div>目錄 {fmtDate(catalogAt)}</div>
          <div>人數 {fmtDate(enrollAt)}</div>
        </div>
      </header>

      {status === "error" && (
        <GlassPanel className="mx-4 mb-2 p-4 text-sm text-red-600">載入失敗：{error}（請重試）</GlassPanel>
      )}

      {staleDropped.length > 0 && (
        <GlassPanel className="mx-4 mb-2 flex items-center justify-between gap-3 p-3 text-sm text-amber-700">
          <span>已移除 {staleDropped.length} 門在本學期資料中不存在的課程（草稿已更新）</span>
          <button onClick={dismissStale} className="shrink-0 rounded-lg px-2 py-0.5 text-xs hover:bg-amber-500/10" aria-label="關閉提示">
            關閉
          </button>
        </GlassPanel>
      )}

      <div className="flex min-h-0 flex-1 gap-3 px-3 pb-3 sm:px-4">
        {/* timetable */}
        <GlassPanel className="min-h-0 flex-1 overflow-auto p-3 sm:p-4">
          {status === "loading" ? (
            <div className="flex h-full items-center justify-center text-sm text-[var(--ink-soft)]">載入課程中…</div>
          ) : (
            <WeeklyGrid />
          )}
        </GlassPanel>

        {/* desktop course library + favorites */}
        <GlassPanel className="hidden w-[380px] min-h-0 shrink-0 flex-col overflow-hidden lg:flex">
          <div className="min-h-0 flex-1">
            <CourseLibrary />
          </div>
          <FavoritesPanel />
        </GlassPanel>
      </div>

      <CreditSummary />

      {/* mobile bottom-sheet library */}
      <div className="lg:hidden">
        <Sheet open={libraryOpen} onOpenChange={(o) => setLibraryOpen(o)}>
          <SheetTrigger
            render={
              <Button className="fixed bottom-20 right-4 z-30 h-12 rounded-full px-5 shadow-lg" />
            }
          >
            課程庫
          </SheetTrigger>
          <SheetContent side="bottom" className="glass-surface h-[82dvh] rounded-t-3xl p-0">
            <CourseLibrary />
          </SheetContent>
        </Sheet>
      </div>

      <SlotPopover />
      <CourseDetailDrawer />
    </main>
  );
}

function FavoritesPanel() {
  return (
    <div className="shrink-0 border-t border-black/5">
      <div className="px-4 pt-2.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--ink-soft)]">收藏 · 帶選</div>
      <div className="thin-scroll max-h-44 overflow-y-auto">
        <FavoritesList />
      </div>
    </div>
  );
}
