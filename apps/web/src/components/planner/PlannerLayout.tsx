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

export function PlannerLayout() {
  const status = useTermStore((s) => s.status);
  const error = useTermStore((s) => s.error);
  const catalogAt = useTermStore((s) => s.catalogCrawledAt());
  const enrollAt = useTermStore((s) => s.enrollmentObservedAt());
  const libraryOpen = useUiStore((s) => s.libraryOpen);
  const setLibraryOpen = useUiStore((s) => s.setLibraryOpen);

  return (
    <main className="flex h-dvh flex-col">
      <header className="flex items-center gap-3 px-4 py-2">
        <h1 className="text-base font-semibold">北科盒子 排課</h1>
        <TermSwitcher />
        <span className="ml-auto text-[10px] text-zinc-400">
          目錄 {catalogAt ?? "—"}｜人數 {enrollAt ?? "—"}
        </span>
      </header>

      {status === "error" && (
        <GlassPanel className="m-4 p-4 text-sm text-red-600">
          載入失敗：{error}（請重試）
        </GlassPanel>
      )}

      <div className="flex min-h-0 flex-1 gap-3 px-3 pb-2">
        {/* grid main */}
        <GlassPanel className="min-h-0 flex-1 overflow-auto p-3">
          {status === "loading" ? (
            <p className="text-sm text-zinc-500">載入中…</p>
          ) : (
            <WeeklyGrid />
          )}
        </GlassPanel>
        {/* desktop side library */}
        <GlassPanel className="hidden min-h-0 w-[360px] flex-col overflow-hidden lg:flex">
          <CourseLibrary />
          <div className="border-t">
            <FavoritesList />
          </div>
        </GlassPanel>
      </div>

      <CreditSummary />

      {/* mobile bottom-sheet library */}
      <div className="lg:hidden">
        <Sheet open={libraryOpen} onOpenChange={(o) => setLibraryOpen(o)}>
          <SheetTrigger
            render={
              <Button className="fixed bottom-16 right-4 rounded-full shadow-lg" />
            }
          >
            課程庫
          </SheetTrigger>
          <SheetContent side="bottom" className="h-[80dvh] p-0">
            <CourseLibrary />
          </SheetContent>
        </Sheet>
      </div>

      <SlotPopover />
      <CourseDetailDrawer />
    </main>
  );
}
