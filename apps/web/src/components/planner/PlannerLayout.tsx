"use client";
import { useTermStore } from "@/store/term-store";
import { useUiStore } from "@/store/ui-store";
import { useDraftStore } from "@/store/draft-store";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/glass/GlassPanel";
import { WeeklyGrid } from "./WeeklyGrid";
import { CourseLibrary } from "./CourseLibrary";
import { SlotPopover } from "./SlotPopover";
import { CourseDetailDrawer } from "./CourseDetailDrawer";
import { CreditSummary } from "./CreditSummary";
import { TermSwitcher } from "./TermSwitcher";
import { MatricSwitcher } from "./MatricSwitcher";
import { FavoritesList } from "./FavoritesList";
import { NoTimeTray } from "./NoTimeTray";
import { Toaster } from "@/components/ui/toast";
import { useShareLink } from "@/lib/planner/use-share-link";

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
  useShareLink();

  return (
    <main className="flex h-dvh flex-col">
      <header className="flex items-center gap-3 px-4 pt-4 pb-2 sm:px-5">
        <h1 className="text-lg font-bold tracking-tight text-[var(--ink)]">
          北科盒子 <span className="text-[var(--accent)]">排課</span>
        </h1>
        <TermSwitcher />
        <MatricSwitcher />
        <div className="ml-auto hidden items-center gap-1.5 text-[11px] text-[var(--ink-faint)] sm:flex">
          <span>資料更新</span>
          <span className="font-medium text-[var(--ink-soft)]">{fmtDate(enrollAt ?? catalogAt)}</span>
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
        <GlassPanel className="flex min-h-0 flex-1 flex-col overflow-hidden p-3 sm:p-4">
          <MobileViewControls />
          <div className="min-h-0 flex-1 overflow-auto">
            {status === "loading" ? (
              <div className="flex h-full items-center justify-center text-sm text-[var(--ink-soft)]">載入課程中…</div>
            ) : (
              <WeeklyGrid />
            )}
          </div>
          <NoTimeTray />
        </GlassPanel>

        {/* desktop right panel: 課程庫 / 收藏 toggle */}
        <GlassPanel className="hidden w-[380px] min-h-0 shrink-0 flex-col overflow-hidden lg:flex">
          <RightPanel />
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
          <SheetContent side="bottom" className="glass-surface flex flex-col gap-0 overflow-hidden rounded-t-3xl p-0 data-[side=bottom]:h-[82dvh]">
            <RightPanel />
          </SheetContent>
        </Sheet>
      </div>

      <SlotPopover />
      <CourseDetailDrawer />
      <Toaster />
    </main>
  );
}

const DAY_LABEL: Record<number, string> = { 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六" };

// Mobile-only: 週/日 view toggle + day picker (desktop always shows the full week).
function MobileViewControls() {
  const viewMode = useUiStore((s) => s.viewMode);
  const setViewMode = useUiStore((s) => s.setViewMode);
  const selectedDay = useUiStore((s) => s.selectedDay);
  const setSelectedDay = useUiStore((s) => s.setSelectedDay);

  return (
    <div className="mb-2 flex items-center gap-2 lg:hidden">
      <div className="flex rounded-full bg-black/5 p-0.5 text-xs font-semibold">
        {(["week", "day"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setViewMode(m)}
            className={
              "rounded-full px-3 py-1 transition-colors " +
              (viewMode === m ? "bg-white text-[var(--ink)] shadow-sm" : "text-[var(--ink-soft)]")
            }
          >
            {m === "week" ? "週" : "日"}
          </button>
        ))}
      </div>
      {viewMode === "day" && (
        <div className="thin-scroll flex gap-1 overflow-x-auto">
          {[1, 2, 3, 4, 5, 6].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setSelectedDay(d)}
              className={
                "flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors " +
                (selectedDay === d ? "bg-[var(--accent)] text-white" : "bg-white/70 text-[var(--ink-soft)]")
              }
            >
              {DAY_LABEL[d]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function RightPanel() {
  const tab = useUiStore((s) => s.libraryTab);
  const setTab = useUiStore((s) => s.setLibraryTab);
  const favCount = useDraftStore((s) => s.favorites.length);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex gap-1 px-3 pt-3">
        <PanelTab active={tab === "courses"} onClick={() => setTab("courses")}>課程庫</PanelTab>
        <PanelTab active={tab === "favorites"} onClick={() => setTab("favorites")}>
          收藏{favCount > 0 ? ` ${favCount}` : ""}
        </PanelTab>
      </div>
      <div className="min-h-0 flex-1">
        {tab === "courses" ? <CourseLibrary /> : <div className="thin-scroll h-full overflow-y-auto p-2"><FavoritesList /></div>}
      </div>
    </div>
  );
}

function PanelTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "rounded-full px-4 py-1.5 text-sm font-semibold transition-colors " +
        (active ? "bg-[var(--accent)] text-white shadow-sm" : "text-[var(--ink-soft)] hover:bg-black/5")
      }
    >
      {children}
    </button>
  );
}
