import { describe, expect, it } from "vitest";
import { cellRoom, courseRoomsView, formatCourseRooms, formatPeriodRanges } from "./meeting-rooms";

type M = { day: number; periods: string[]; classroom_codes?: string[] };
const course = (meetings: M[], rooms: [string, string][]) =>
  ({
    classrooms: rooms.map(([code, name]) => ({ code, name })),
    meetings,
  }) as unknown as Parameters<typeof formatCourseRooms>[0];

// 115-1 360745 英文：週四 5–6 六教526、週五 7 六教626
const multi = course(
  [
    { day: 4, periods: ["5", "6"], classroom_codes: ["438"] },
    { day: 5, periods: ["7"], classroom_codes: ["446"] },
  ],
  [["438", "六教526(e)"], ["446", "六教626(e)"]],
);

describe("formatPeriodRanges", () => {
  it("併相鄰節次、依節次順序", () => {
    expect(formatPeriodRanges(["5", "6"])).toBe("5–6");
    expect(formatPeriodRanges(["7"])).toBe("7");
    expect(formatPeriodRanges(["8", "5", "6"])).toBe("5–6、8");
    expect(formatPeriodRanges(["1", "2", "3", "4"])).toBe("1–4");
  });
  it("N 在 4 與 5 之間；少了 N 就不相鄰", () => {
    expect(formatPeriodRanges(["4", "N", "5"])).toBe("4–5");
    expect(formatPeriodRanges(["4", "5"])).toBe("4、5");
    expect(formatPeriodRanges(["9", "A", "B"])).toBe("9–B");
  });
});

describe("formatCourseRooms", () => {
  it("多教室課逐時段列出", () => {
    expect(formatCourseRooms(multi)).toBe("週四 5–6　六教526(e) ／ 週五 7　六教626(e)");
  });
  it("全部時段同一間 → 只列教室", () => {
    const c = course(
      [
        { day: 1, periods: ["1", "2"], classroom_codes: ["438"] },
        { day: 3, periods: ["3"], classroom_codes: ["438"] },
      ],
      [["438", "六教526(e)"]],
    );
    expect(formatCourseRooms(c)).toBe("六教526(e)");
  });
  it("沒有逐時段資料 → 課程層級清單（與之前相同）", () => {
    const c = course([{ day: 4, periods: ["5"] }, { day: 5, periods: ["7"], classroom_codes: [] }], [
      ["438", "六教526(e)"],
      ["446", "六教626(e)"],
    ]);
    expect(courseRoomsView(c)).toEqual({ kind: "list", rooms: ["六教526(e)", "六教626(e)"] });
    expect(formatCourseRooms(c)).toBe("六教526(e)、六教626(e)");
  });
  it("都沒有教室 → —", () => {
    expect(formatCourseRooms(course([{ day: 1, periods: ["1"] }], []))).toBe("—");
  });
  it("部分時段查不到 → 該時段退回課程層級清單", () => {
    const c = course(
      [
        { day: 4, periods: ["5", "6"], classroom_codes: ["438"] },
        { day: 5, periods: ["7"], classroom_codes: [] },
      ],
      [["438", "六教526(e)"], ["446", "六教626(e)"]],
    );
    const v = courseRoomsView(c);
    expect(v.kind).toBe("lines");
    if (v.kind === "lines") expect(v.lines.map((l) => l.exact)).toEqual([true, false]);
    expect(formatCourseRooms(c)).toBe("週四 5–6　六教526(e) ／ 週五 7　六教526(e)、六教626(e)");
  });
  it("code 對不到名稱 → 視同查不到", () => {
    const c = course([{ day: 1, periods: ["1"], classroom_codes: ["999"] }], [["438", "六教526(e)"]]);
    expect(formatCourseRooms(c)).toBe("六教526(e)");
  });
});

describe("cellRoom", () => {
  it("該格的教室", () => {
    expect(cellRoom(multi, 4, "6")).toBe("六教526(e)");
    expect(cellRoom(multi, 5, "7")).toBe("六教626(e)");
  });
  it("查不到 → 列出課程層級全部教室（多教室不猜其中一間）", () => {
    const c = course([{ day: 4, periods: ["5"] }], [["438", "六教526(e)"], ["446", "六教626(e)"]]);
    expect(cellRoom(c, 4, "5")).toBe("六教526(e)、六教626(e)");
    const single = course([{ day: 4, periods: ["5"] }], [["438", "六教526(e)"]]);
    expect(cellRoom(single, 4, "5")).toBe("六教526(e)");
    expect(cellRoom(course([{ day: 4, periods: ["5"] }], []), 4, "5")).toBeUndefined();
  });
});
