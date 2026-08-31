"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
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
import { SharedTimetableModal } from "./SharedTimetableModal";
import { SharedPlanFab } from "./SharedPlanFab";
import { CreditSummary } from "./CreditSummary";
import { AboutDialog } from "./AboutDialog";
import { CourseJsonLd } from "./CourseJsonLd";
import { TermSwitcher } from "./TermSwitcher";
import { MatricSwitcher } from "./MatricSwitcher";
import { FavoritesList } from "./FavoritesList";
import { MicroProgramPane } from "./MicroProgramPane";
import { NoTimeTray } from "./NoTimeTray";
import { Toaster } from "@/components/ui/toast";
import { useShareLink } from "@/lib/planner/use-share-link";
import { useCourseTitle } from "@/lib/planner/use-course-title";

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
  const belowLg = useBelowLg();
  useShareLink();
  useCourseTitle();

  return (
    <main className="flex h-dvh flex-col">
      <header className="flex items-center gap-3 px-4 pt-4 pb-2 sm:px-5">
        <h1 className="text-lg font-bold tracking-tight text-[var(--ink)]">
          北科盒子 <span className="text-[var(--accent)]">排課</span>
        </h1>
        <TermSwitcher />
        <MatricSwitcher />
        <div className="ml-auto flex items-center gap-1">
          <div className="mr-1 hidden items-center gap-1.5 text-[11px] text-[var(--ink-faint)] sm:flex">
            <span>資料更新</span>
            <span className="font-medium text-[var(--ink-soft)]">{fmtDate(enrollAt ?? catalogAt)}</span>
          </div>
          {/* 兩個內容入口都要：排課器是 app shell、沒有頁尾，這些頁若沒有站內連結
              就是孤兒頁（爬蟲只能從 sitemap 找到）。
              「課程總覽」用 hidden sm:inline-flex——實測 390px 視寬塞不進這條 header
              （會把 h1 擠成兩行並產生 4px 橫向溢出），行動版的入口放在下方
              MobileViewControls 那排。兩者的 anchor 在兩種視寬都存在於靜態 HTML，
              不執行 JS 的爬蟲都讀得到。 */}
          <Link
            href="/browse/"
            className="hidden shrink-0 rounded-lg px-2 py-2 text-[11px] font-medium text-[var(--ink-faint)] transition-colors hover:bg-[var(--accent)]/10 hover:text-[var(--accent-ink)] sm:inline-flex"
          >
            課程總覽
          </Link>
          <Link
            href="/guide/"
            className="shrink-0 rounded-lg px-2 py-2 text-[11px] text-[var(--ink-faint)] transition-colors hover:bg-[var(--accent)]/10 hover:text-[var(--accent-ink)]"
          >
            選課指南
          </Link>
          <AboutDialog />
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
          {/* pb-7 lg:pb-0：窄機的「課程庫」FAB（fixed bottom-28）會壓在課表右下角，
              捲到底時覆蓋週五 D 節約 61%（實測），該格幾乎點不到。
              實測容器底緣到 FAB 頂只差 25px，給 28px 剛好讓最後一列停在 FAB 上方——
              不要給整個 FAB 高度（56px），那會留下明顯過多的底部空白。
              桌面沒有 FAB，不需要這段留白。 */}
          <div className="min-h-0 flex-1 overflow-auto pb-7 lg:pb-0">
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
      <CourseJsonLd />

      {/* mobile bottom-sheet library — gate open by viewport: SheetContent portals to
          <body> and escapes this lg:hidden wrapper, so on desktop libraryOpen (set by
          openProgram 的微學程 chip) would otherwise stack the sheet over the常駐右欄。 */}
      <div className="lg:hidden">
        <Sheet open={libraryOpen && belowLg} onOpenChange={(o) => setLibraryOpen(o)}>
          <SheetTrigger
            render={
              <Button className="fixed bottom-28 right-4 z-30 h-12 rounded-full px-5 shadow-lg sm:bottom-20" />
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
      <SharedTimetableModal />
      <SharedPlanFab />
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
      {/* 行動版的 hub 入口。這排本來只放週/日 pill、右側是空的 → 加連結不佔額外高度，
          也不會像 header 那樣把標題擠成兩行。日檢視時排在星期選擇器之後。 */}
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
      <Link
        href="/browse/"
        className="ml-auto shrink-0 rounded-lg px-2 py-1 text-[11px] font-medium text-[var(--accent-ink)] transition-colors hover:bg-[var(--accent)]/10"
      >
        課程總覽 →
      </Link>
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
        <PanelTab active={tab === "programs"} onClick={() => setTab("programs")}>微學程</PanelTab>
      </div>
      <div className="min-h-0 flex-1">
        {tab === "courses" ? (
          <CourseLibrary />
        ) : tab === "favorites" ? (
          <div className="thin-scroll h-full overflow-y-auto p-2">
            <FavoritesList />
          </div>
        ) : (
          <MicroProgramPane />
        )}
      </div>
    </div>
  );
}

// true 當視窗 < lg(1024px)。SSR/首繪預設 false（桌機不閃 sheet）；掛載後才依 matchMedia 校正。
function useBelowLg() {
  const [below, setBelow] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(max-width: 1023px)");
    const sync = () => setBelow(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return below;
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
