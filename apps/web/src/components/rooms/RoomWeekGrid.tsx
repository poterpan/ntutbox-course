/**
 * 教室整週課表（D25）：純展示，星期（一～六＋有課才顯示日）× 節次。
 * 不是 planner 的 WeeklyGrid（那個綁 draft／ui store 與互動）；節次順序與視覺 token 沿用。
 *
 * - 同一天相鄰節次排的是同一組課 → 合併成一塊（gridRow span），三節課不重複寫三次。
 * - 同格多課全列（學校課表可能把多門課排在同一間同一節）。
 * - `today`／`active` 由 client 在 mount 後才給（靜態 HTML 不帶時間狀態）。
 *
 * 不加 "use client"：本身無 hook，server 與 client 都能 render。
 */
import Link from "next/link";
import { cn } from "@/lib/utils";
import type { RoomSlotView } from "@/lib/rooms/rooms-view";

export interface GridPeriod {
  token: string;
  start_hm: string;
  end_hm: string;
}

const DAY_LABEL: Record<number, string> = { 0: "日", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六" };

export function gridDays(slots: readonly RoomSlotView[]): number[] {
  const days = [1, 2, 3, 4, 5, 6];
  if (slots.some((s) => s.day === 0)) days.push(0);
  return days;
}

interface Block {
  day: number;
  startIdx: number;
  span: number;
  slot: RoomSlotView | null;
  periods: string[];
}

function sameCourses(a: RoomSlotView | undefined, b: RoomSlotView | undefined): boolean {
  if (!a || !b || a.courses.length === 0) return false;
  const ka = a.courses.map((c) => c.offeringId).join(",");
  return ka === b.courses.map((c) => c.offeringId).join(",");
}

function buildBlocks(day: number, tokens: string[], slots: readonly RoomSlotView[]): Block[] {
  const at = new Map(slots.filter((s) => s.day === day).map((s) => [s.period, s]));
  const blocks: Block[] = [];
  for (let i = 0; i < tokens.length; i++) {
    const slot = at.get(tokens[i]!);
    const last = blocks[blocks.length - 1];
    if (slot && slot.courses.length > 0 && last?.slot && sameCourses(last.slot, slot) && last.startIdx + last.span === i) {
      last.span += 1;
      last.periods.push(tokens[i]!);
    } else {
      blocks.push({ day, startIdx: i, span: 1, slot: slot && slot.courses.length > 0 ? slot : null, periods: [tokens[i]!] });
    }
  }
  return blocks;
}

export function RoomWeekGrid({
  periods,
  slots,
  today = null,
  active = null,
}: {
  periods: readonly GridPeriod[];
  slots: readonly RoomSlotView[];
  /** 台北時間今天（0=日…6=六）；未知（SSR）→ null */
  today?: number | null;
  /** 目前這一節（節內或節間歸下一節）；null＝不標亮 */
  active?: { day: number; period: string } | null;
}) {
  const days = gridDays(slots);
  const tokens = periods.map((p) => p.token);

  return (
    // 頁面本身不能橫捲：只有課表這塊在窄螢幕內部橫向捲動。relative 必要——內部的 absolute（sr-only）
    // 若沒有定位祖先會逃出 overflow 裁切、把整頁撐寬。
    <div className="thin-scroll group relative -mx-4 overflow-x-auto px-4 pb-2 pt-1 sm:mx-0 sm:px-0">
      <div
        role="group"
        aria-label="教室週課表"
        className="grid min-w-[640px] gap-1 [--label-col:2.25rem] sm:[--label-col:3rem]"
        style={{
          gridTemplateColumns: `var(--label-col) repeat(${days.length}, minmax(0, 1fr))`,
          gridTemplateRows: `2rem repeat(${tokens.length}, minmax(2.75rem, auto))`,
        }}
      >
        {/* 手機橫捲時的節次欄底：一整條連續玻璃欄（節次格本身透明，避免格間縫透出課格）；
            課表往右捲了（RoomTimetable 設 data-scrolled）才在右緣加陰影。
            捲動容器有 px-4、sticky 以內容邊為準 → -left-4＋-ml-4／pl-4 讓欄貼齊容器左緣。 */}
        <div
          aria-hidden
          style={{ gridColumn: 1, gridRow: "1 / -1" }}
          className="sticky -left-4 z-[5] -my-1 -ml-4 border-r border-black/[0.06] bg-[var(--glass-bg)] backdrop-blur-md transition-shadow duration-200 group-data-[scrolled=true]:shadow-[8px_0_12px_-10px_rgba(15,23,42,0.45)] sm:hidden dark:border-white/10"
        />
        <div
          style={{ gridColumn: 1, gridRow: 1 }}
          className="sticky -left-4 z-10 -ml-4 pl-4 sm:static sm:ml-0 sm:pl-0"
        />
        {days.map((d, ci) => {
          const isToday = today === d;
          return (
            <div
              key={d}
              style={{ gridColumn: ci + 2, gridRow: 1 }}
              className="flex items-center justify-center"
              data-today={isToday || undefined}
            >
              <span
                className={cn(
                  "rounded-full px-2.5 py-0.5 text-[13px] font-semibold",
                  isToday ? "bg-[var(--accent)] text-white shadow-sm" : "text-[var(--ink-soft)]",
                )}
                aria-current={isToday ? "date" : undefined}
              >
                週{DAY_LABEL[d]}
                {isToday && <span className="sr-only">（今天）</span>}
              </span>
            </div>
          );
        })}

        {periods.map((p, ri) => {
          const muted = p.token === "N" || ["A", "B", "C", "D"].includes(p.token);
          return (
            <div
              key={p.token}
              style={{ gridColumn: 1, gridRow: ri + 2 }}
              className="sticky -left-4 z-10 -ml-4 flex flex-col items-center justify-center pl-4 leading-none sm:static sm:ml-0 sm:pl-0"
            >
              <span className={cn("text-xs font-semibold text-[var(--ink-soft)]", muted && "opacity-75")}>{p.token}</span>
              <span className={cn("mt-0.5 text-[9px] tabular-nums text-[var(--ink-faint)]", muted && "opacity-75")}>
                {p.start_hm}
              </span>
            </div>
          );
        })}

        {days.flatMap((d, ci) =>
          buildBlocks(d, tokens, slots).map((b) => {
            const isActive = active != null && active.day === d && b.periods.includes(active.period);
            const isToday = today === d;
            return (
              <div
                key={`${d}-${b.startIdx}`}
                data-testid={b.slot ? "room-slot" : undefined}
                data-active={isActive || undefined}
                style={{ gridColumn: ci + 2, gridRow: `${b.startIdx + 2} / span ${b.span}` }}
                className={cn(
                  "relative min-w-0 rounded-md p-1.5 text-[11px] leading-snug",
                  b.slot
                    ? "border-l-[3px] border-[var(--accent)] bg-[var(--accent)]/[0.13] text-[var(--ink)]"
                    : cn(
                        "ring-1 ring-inset ring-black/[0.06] dark:ring-white/10",
                        isToday ? "bg-[var(--accent)]/[0.05]" : "bg-white/40 dark:bg-white/[0.03]",
                      ),
                  isActive && "ring-2 ring-orange-500 ring-offset-1 ring-offset-transparent",
                )}
              >
                {isActive && (
                  <span className="absolute -top-2 right-1 rounded-full bg-orange-700 px-1.5 py-px text-[9px] font-bold text-white shadow-sm">
                    現在
                  </span>
                )}
                {b.slot && (
                  <ul className="flex flex-col gap-1">
                    {b.slot.courses.map((c) => (
                      <li key={c.offeringId} className="min-w-0">
                        {c.href ? (
                          <Link href={c.href} className="block font-semibold text-[var(--ink)] hover:text-[var(--accent-ink)] hover:underline">
                            {c.name ?? `課號 ${c.offeringId}`}
                          </Link>
                        ) : (
                          <span className="block font-semibold text-[var(--ink)]">{c.name ?? `課號 ${c.offeringId}`}</span>
                        )}
                        {c.teachers && <span className="block truncate text-[10px] text-[var(--ink-soft)]">{c.teachers}</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          }),
        )}
      </div>
    </div>
  );
}
