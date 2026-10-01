/**
 * 教室頁的「現在／下一堂」（D25）。純函式；只在 client mount 後呼叫（靜態 HTML 不含時間狀態，
 * 避免 build 時刻凍結進頁面、也避免 hydration mismatch）。
 *
 * 規則：
 * - 以 periods.json 的 `timezone`（Asia/Taipei）取星期與時:分，對 `start_hm`／`end_hm`。
 * - 節內 → `active`（inSession=true）；節與節之間 → 歸下一節（inSession=false）。
 * - 第一節之前、最後一節之後 → 沒有 active，只給 `next`。
 * - `next`：active 之後（沒有 active 就是「現在」之後）第一個有排課的節次，跨週繞回。
 * 不讀行事曆：考試週／假期由頁面的「依課表」語意涵蓋。
 */

export interface PeriodLike {
  token: string;
  order: number;
  start_hm: string;
  end_hm: string;
}

export interface PeriodsLike {
  timezone?: string | null;
  periods?: PeriodLike[] | null;
}

export interface SlotLike {
  day: number;
  period: string;
}

export interface RoomNow<S extends SlotLike> {
  /** 台北時間的星期（0=日 … 6=六）。 */
  today: number;
  /** 「目前這一節」：節內或節間（歸下一節）；其他時間 null。 */
  active: {
    period: string;
    start_hm: string;
    end_hm: string;
    /** true＝正在節內；false＝下課時間、歸到下一節 */
    inSession: boolean;
    /** 該節的排課（同格多課全列）；沒排課＝[] */
    slots: S[];
  } | null;
  /** 下一個有排課的節次；整週都沒排課 → null。 */
  next: {
    day: number;
    period: string;
    start_hm: string;
    slots: S[];
    /** 0＝今天、1＝明天…；7＝下週同一天（跨週繞回到今天稍早的節次）。 */
    daysAhead: number;
  } | null;
}

const WEEKDAY: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

/** 指定時區的星期與「當天第幾分鐘」。 */
export function zonedDayMinute(now: Date, timeZone: string): { day: number; minute: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const hour = Number(get("hour")) % 24;
  return { day: WEEKDAY[get("weekday")] ?? 0, minute: hour * 60 + Number(get("minute")) };
}

function hm(s: string): number {
  const [h, m] = s.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

export function roomNow<S extends SlotLike>(now: Date, periods: PeriodsLike, slots: readonly S[]): RoomNow<S> {
  const tz = periods.timezone || "Asia/Taipei";
  const { day: today, minute } = zonedDayMinute(now, tz);
  const ordered = [...(periods.periods ?? [])].sort((a, b) => a.order - b.order);

  const at = (day: number, period: string) => slots.filter((s) => s.day === day && s.period === period);

  // 目前這一節：節內，或還沒開始但前一節已開始過（＝節間）
  let activeIdx = -1;
  let inSession = false;
  for (let i = 0; i < ordered.length; i++) {
    const p = ordered[i]!;
    const start = hm(p.start_hm);
    const end = hm(p.end_hm);
    if (minute >= start && minute < end) {
      activeIdx = i;
      inSession = true;
      break;
    }
    if (minute < start) {
      if (i > 0) activeIdx = i; // 節間 → 歸下一節；i===0 是第一節之前，不算
      break;
    }
  }

  const active =
    activeIdx >= 0
      ? {
          period: ordered[activeIdx]!.token,
          start_hm: ordered[activeIdx]!.start_hm,
          end_hm: ordered[activeIdx]!.end_hm,
          inSession,
          slots: at(today, ordered[activeIdx]!.token),
        }
      : null;

  // 下一堂：從 active 之後（或現在之後）開始找，跨週繞回
  let startIdx: number;
  if (activeIdx >= 0) startIdx = activeIdx + 1;
  else {
    const firstAfter = ordered.findIndex((p) => minute < hm(p.start_hm));
    startIdx = firstAfter >= 0 ? firstAfter : ordered.length;
  }
  let next: RoomNow<S>["next"] = null;
  outer: for (let k = 0; k <= 7; k++) {
    const day = (today + k) % 7;
    const from = k === 0 ? startIdx : 0;
    const to = k === 7 ? startIdx : ordered.length; // 第 7 天＝下週今天，只看今天已過的節次
    for (let i = from; i < to; i++) {
      const p = ordered[i]!;
      const here = at(day, p.token);
      if (here.length > 0) {
        next = { day, period: p.token, start_hm: p.start_hm, slots: here, daysAhead: k };
        break outer;
      }
    }
  }

  return { today, active, next };
}
