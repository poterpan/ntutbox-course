"use client";
/**
 * 教室頁的「現在／下一堂」列＋週課表（D25）。
 *
 * 時間狀態只在 mount 後才算（初次 render＝靜態 HTML 不帶狀態，避免 hydration mismatch
 * 與把 build 時刻凍結進頁面）；之後每分鐘、以及分頁回到前景（visibilitychange）時重算。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { roomNow, type PeriodsLike } from "@/lib/rooms/room-now";
import type { RoomCourseRef, RoomSlotView } from "@/lib/rooms/rooms-view";
import { RoomWeekGrid, type GridPeriod } from "./RoomWeekGrid";

const DAY_LABEL = ["日", "一", "二", "三", "四", "五", "六"];

export function useNow(): Date | null {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const tick = () => setNow(new Date());
    tick();
    const id = window.setInterval(tick, 60_000);
    const onVis = () => { if (document.visibilityState === "visible") tick(); };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);
  return now;
}

function courseNames(courses: RoomCourseRef[]): string {
  return courses.map((c) => c.name ?? `課號 ${c.offeringId}`).join("、");
}

function whenLabel(daysAhead: number, day: number): string {
  if (daysAhead === 0) return "今天";
  if (daysAhead === 1) return "明天";
  if (daysAhead === 7) return `下週${DAY_LABEL[day]}`;
  return `週${DAY_LABEL[day]}`;
}

export function RoomTimetable({
  timezone,
  periods,
  slots,
}: {
  timezone: string | null;
  periods: GridPeriod[];
  slots: RoomSlotView[];
}) {
  const now = useNow();
  const table: PeriodsLike = useMemo(
    () => ({ timezone, periods: periods.map((p, i) => ({ ...p, order: i })) }),
    [timezone, periods],
  );
  const state = useMemo(() => (now ? roomNow(now, table, slots) : null), [now, table, slots]);
  const active = state?.active ?? null;

  // 手機寬度課表要橫捲：今天那欄不在畫面內時捲過去（只動課表本身的 scrollLeft，不動整頁）。
  const gridRef = useRef<HTMLDivElement>(null);
  const today = state?.today ?? null;
  useEffect(() => {
    const scroller = gridRef.current?.firstElementChild;
    const head = gridRef.current?.querySelector<HTMLElement>("[data-today]");
    if (!(scroller instanceof HTMLElement) || !head) return;
    const s = scroller.getBoundingClientRect();
    const h = head.getBoundingClientRect();
    if (h.left < s.left || h.right > s.right) {
      scroller.scrollLeft += h.left - s.left - (s.width - h.width) / 2;
    }
  }, [today]);

  // 課表往右捲了 → data-scrolled，讓節次欄右緣出陰影（RoomWeekGrid 的 group-data-[scrolled=true]）。
  useEffect(() => {
    const scroller = gridRef.current?.firstElementChild;
    if (!(scroller instanceof HTMLElement)) return;
    const sync = () => {
      scroller.setAttribute("data-scrolled", String(scroller.scrollLeft > 4));
    };
    sync();
    scroller.addEventListener("scroll", sync, { passive: true });
    return () => scroller.removeEventListener("scroll", sync);
  }, [today]);

  return (
    <div className="flex flex-col gap-3">
      <div
        aria-live="polite"
        className="min-h-[3.25rem] rounded-xl bg-white/70 px-3.5 py-2.5 text-sm ring-1 ring-black/[0.07] dark:bg-white/[0.06] dark:ring-white/10"
      >
        {!state ? (
          <span className="text-[var(--ink-soft)]">依課表推算目前狀態…</span>
        ) : (
          <div className="flex flex-col gap-1">
            {active && (
              <p className="flex flex-wrap items-baseline gap-x-2">
                <span
                  className={
                    active.slots.length > 0
                      ? "rounded-full bg-orange-700 px-2 py-0.5 text-xs font-bold text-white"
                      : "rounded-full bg-emerald-700 px-2 py-0.5 text-xs font-bold text-white"
                  }
                >
                  {active.inSession ? `第 ${active.period} 節` : `下一節 第 ${active.period} 節`}
                </span>
                <span className="font-semibold text-[var(--ink)]">
                  {active.slots.length > 0
                    ? courseNames(active.slots.flatMap((s) => s.courses))
                    : "依課表沒排課"}
                </span>
                <span className="text-xs tabular-nums text-[var(--ink-soft)]">
                  {active.inSession ? `到 ${active.end_hm}` : `${active.start_hm}–${active.end_hm}`}
                </span>
              </p>
            )}
            {!active && <p className="text-[var(--ink-soft)]">現在不是上課節次。</p>}
            <p className="text-[var(--ink-soft)]">
              {state.next ? (
                <>
                  下一堂：
                  <span className="font-medium text-[var(--ink)]">
                    {whenLabel(state.next.daysAhead, state.next.day)} 第 {state.next.period} 節（{state.next.start_hm}）
                  </span>{" "}
                  {courseNames(state.next.slots.flatMap((s) => s.courses))}
                </>
              ) : (
                "本週依課表都沒有排課。"
              )}
            </p>
          </div>
        )}
      </div>

      <div ref={gridRef}>
        <RoomWeekGrid
          periods={periods}
          slots={slots}
          today={state?.today ?? null}
          active={active && state ? { day: state.today, period: active.period } : null}
        />
      </div>
    </div>
  );
}
