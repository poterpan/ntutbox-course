import { describe, expect, it } from "vitest";
import { roomNow, zonedDayMinute } from "./room-now";

// 115-1 periods.json 的節次表（Asia/Taipei）
const PERIODS = {
  timezone: "Asia/Taipei",
  periods: [
    ["1", "08:10", "09:00"], ["2", "09:10", "10:00"], ["3", "10:10", "11:00"], ["4", "11:10", "12:00"],
    ["N", "12:10", "13:00"], ["5", "13:10", "14:00"], ["6", "14:10", "15:00"], ["7", "15:10", "16:00"],
    ["8", "16:10", "17:00"], ["9", "17:10", "18:00"], ["A", "18:30", "19:20"], ["B", "19:20", "20:10"],
    ["C", "20:20", "21:10"], ["D", "21:10", "22:00"],
  ].map(([token, start_hm, end_hm], order) => ({ token: token!, order, start_hm: start_hm!, end_hm: end_hm! })),
};

/** 台北時間 → Date（2026-09-28 是週一）。 */
function taipei(date: string, hm: string): Date {
  return new Date(`${date}T${hm}:00+08:00`);
}
const MON = "2026-09-28";
const WED = "2026-09-30";
const SAT = "2026-10-03";
const SUN = "2026-10-04";

const slot = (day: number, period: string, id: string) => ({ day, period, id });

describe("zonedDayMinute", () => {
  it("UTC 05:30 週一 → 台北 13:30 週一", () => {
    expect(zonedDayMinute(new Date("2026-09-28T05:30:00Z"), "Asia/Taipei")).toEqual({ day: 1, minute: 13 * 60 + 30 });
  });
  it("UTC 週日 20:00 → 台北週一 04:00（跨日）", () => {
    expect(zonedDayMinute(new Date("2026-09-27T20:00:00Z"), "Asia/Taipei")).toEqual({ day: 1, minute: 4 * 60 });
  });
});

describe("roomNow", () => {
  const slots = [slot(1, "5", "A"), slot(1, "6", "A"), slot(3, "2", "B"), slot(3, "2", "C")];

  it("UTC→台北：UTC 05:30 週一＝台北 13:30 第 5 節、上課中", () => {
    const r = roomNow(new Date("2026-09-28T05:30:00Z"), PERIODS, slots);
    expect(r.today).toBe(1);
    expect(r.active).toMatchObject({ period: "5", inSession: true, end_hm: "14:00" });
    expect(r.active!.slots.map((s) => s.id)).toEqual(["A"]);
    // 下一堂從第 5 節之後找：第 6 節
    expect(r.next).toMatchObject({ day: 1, period: "6", daysAhead: 0 });
  });

  it("節內沒排課 → active 存在但 slots 為空", () => {
    const r = roomNow(taipei(MON, "10:30"), PERIODS, slots);
    expect(r.active).toMatchObject({ period: "3", inSession: true });
    expect(r.active!.slots).toEqual([]);
    expect(r.next).toMatchObject({ day: 1, period: "5" });
  });

  it("節與節之間（下課）→ 歸下一節，inSession=false", () => {
    const r = roomNow(taipei(MON, "14:05"), PERIODS, slots);
    expect(r.active).toMatchObject({ period: "6", inSession: false, start_hm: "14:10" });
    expect(r.active!.slots.map((s) => s.id)).toEqual(["A"]);
    expect(r.next).toMatchObject({ day: 3, period: "2", daysAhead: 2 });
  });

  it("剛好在節次結束那一分鐘 → 下課、歸下一節", () => {
    const r = roomNow(taipei(MON, "09:00"), PERIODS, slots);
    expect(r.active).toMatchObject({ period: "2", inSession: false });
  });

  it("早於第 1 節 → 沒有 active，只給下一堂（今天）", () => {
    const r = roomNow(taipei(MON, "07:30"), PERIODS, slots);
    expect(r.active).toBeNull();
    expect(r.next).toMatchObject({ day: 1, period: "5", daysAhead: 0 });
  });

  it("晚於第 D 節 → 沒有 active，下一堂在之後的日子", () => {
    const r = roomNow(taipei(MON, "22:30"), PERIODS, slots);
    expect(r.active).toBeNull();
    expect(r.next).toMatchObject({ day: 3, period: "2", daysAhead: 2 });
  });

  it("週日：節內照樣判定（沒排課），下一堂是週一", () => {
    const r = roomNow(taipei(SUN, "10:30"), PERIODS, slots);
    expect(r.today).toBe(0);
    expect(r.active).toMatchObject({ period: "3", slots: [] });
    expect(r.next).toMatchObject({ day: 1, period: "5", daysAhead: 1 });
  });

  it("跨週下一堂：週六晚上 → 下週一", () => {
    const r = roomNow(taipei(SAT, "20:00"), PERIODS, slots);
    expect(r.next).toMatchObject({ day: 1, period: "5", daysAhead: 2 });
  });

  it("跨週繞回到今天稍早：只有週一第 5 節有課，週一 15:00 → 下週一", () => {
    const only = [slot(1, "5", "A")];
    const r = roomNow(taipei(MON, "15:30"), PERIODS, only);
    expect(r.next).toMatchObject({ day: 1, period: "5", daysAhead: 7 });
  });

  it("正在上的那一節本身是唯一的課 → 下一堂是下週同一節", () => {
    const only = [slot(1, "5", "A")];
    const r = roomNow(taipei(MON, "13:30"), PERIODS, only);
    expect(r.active!.slots.map((s) => s.id)).toEqual(["A"]);
    expect(r.next).toMatchObject({ day: 1, period: "5", daysAhead: 7 });
  });

  it("同格多課：active 與 next 都列出全部", () => {
    const r = roomNow(taipei(WED, "09:20"), PERIODS, slots);
    expect(r.active!.slots.map((s) => s.id)).toEqual(["B", "C"]);
    const before = roomNow(taipei(WED, "08:00"), PERIODS, slots);
    expect(before.next!.slots.map((s) => s.id)).toEqual(["B", "C"]);
  });

  it("整週都沒排課 → next 為 null", () => {
    expect(roomNow(taipei(MON, "10:30"), PERIODS, []).next).toBeNull();
  });
});
