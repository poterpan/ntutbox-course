import type { CourseOffering } from "@/lib/data/types";

/**
 * 逐時段教室（D24）：v1 catalog 的 `meetings[].classroom_codes` 由 derive 以 Croom 教室課表反查填入。
 * 空 list＝查不到 → 退回課程層級 `classrooms`（與 D24 之前相同）。
 * 顯示名一律取該課 `classrooms[].name`（code→name）；對不到名稱的時段視同查不到。
 */

/** 節次順序（非 1..14：中午 N、晚上 A–D）。與 crawler/models.py PERIOD_ORDER 相同。 */
export const PERIOD_SEQUENCE = ["1", "2", "3", "4", "N", "5", "6", "7", "8", "9", "A", "B", "C", "D"] as const;
const DAY = ["日", "一", "二", "三", "四", "五", "六"];
const ORDER = new Map<string, number>(PERIOD_SEQUENCE.map((p, i) => [p, i]));

type RoomCourse = Pick<CourseOffering, "classrooms" | "meetings">;

/** ["5","6","8"] → "5–6、8"；依節次順序、相鄰（含 4→N→5）才併成區間。 */
export function formatPeriodRanges(periods: readonly string[]): string {
  const sorted = [...new Set(periods)].sort((a, b) => (ORDER.get(a) ?? 99) - (ORDER.get(b) ?? 99));
  const runs: string[][] = [];
  for (const p of sorted) {
    const last = runs[runs.length - 1];
    const prev = last?.[last.length - 1];
    const adjacent = prev != null && ORDER.has(p) && ORDER.get(p) === (ORDER.get(prev) ?? -2) + 1;
    if (last && adjacent) last.push(p);
    else runs.push([p]);
  }
  return runs.map((r) => (r.length === 1 ? r[0] : `${r[0]}–${r[r.length - 1]}`)).join("、");
}

function courseRoomNames(c: RoomCourse): string[] {
  return (c.classrooms ?? []).map((r) => r.name).filter((n): n is string => !!n);
}

/** 該時段的教室名稱；查不到（空 codes 或有 code 對不到名稱）→ null。 */
function meetingRoomNames(c: RoomCourse, codes: readonly string[] | undefined): string[] | null {
  if (!codes || codes.length === 0) return null;
  const byCode = new Map((c.classrooms ?? []).map((r) => [r.code, r.name]));
  const names = codes.map((code) => byCode.get(code));
  return names.every((n): n is string => !!n) ? names : null;
}

export interface MeetingRoomLine {
  day: number;
  /** 「週四 5–6」 */
  when: string;
  /** 該時段教室；查不到時為課程層級清單 */
  rooms: string[];
  /** true＝來自逐時段反查；false＝退回課程層級 */
  exact: boolean;
}

/** 課程詳情「教室」列：逐時段（lines）或單一清單（list）。 */
export type CourseRoomsView =
  | { kind: "lines"; lines: MeetingRoomLine[] }
  | { kind: "list"; rooms: string[] };

/**
 * - 沒有任何時段查得到 → 課程層級清單（與之前相同）
 * - 每個時段都查得到、且全是同一組教室 → 那一組（單一教室不必重複列時段）
 * - 其他 → 逐時段一行；查不到的時段退回課程層級清單
 */
export function courseRoomsView(c: RoomCourse): CourseRoomsView {
  const meetings = c.meetings ?? [];
  const resolved = meetings.map((m) => meetingRoomNames(c, m.classroom_codes));
  const fallback = courseRoomNames(c);
  if (!resolved.some(Boolean)) return { kind: "list", rooms: fallback };
  const keys = new Set(resolved.map((r) => JSON.stringify(r)));
  if (resolved.every(Boolean) && keys.size === 1) return { kind: "list", rooms: resolved[0]! };
  return {
    kind: "lines",
    lines: meetings.map((m, i) => ({
      day: m.day,
      when: `週${DAY[m.day] ?? m.day} ${formatPeriodRanges(m.periods as string[])}`,
      rooms: resolved[i] ?? fallback,
      exact: resolved[i] != null,
    })),
  };
}

/** 純文字版：「週四 5–6　六教526 ／ 週五 7　六教626」；單一清單「A、B」；都沒有 → "—"。 */
export function formatCourseRooms(c: RoomCourse): string {
  const v = courseRoomsView(c);
  if (v.kind === "lines") return v.lines.map((l) => `${l.when}　${l.rooms.join("、") || "—"}`).join(" ／ ");
  return v.rooms.join("、") || "—";
}

/** 課表格子（某星期某節）要顯示的教室：該節查得到 → 那間；否則課程層級第一間（與之前相同）。 */
export function cellRoom(c: RoomCourse, day: number, period: string): string | undefined {
  const m = (c.meetings ?? []).find((x) => x.day === day && (x.periods as string[]).includes(period));
  const names = m ? meetingRoomNames(c, m.classroom_codes) : null;
  if (names) return names.join("、");
  return c.classrooms?.[0]?.name || undefined;
}
