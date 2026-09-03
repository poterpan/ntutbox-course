import { describe, it, expect } from "vitest";
import { submitOrder } from "./submit-order";
import type { CourseOffering } from "@/lib/data/types";
import type { PlacedCourse } from "@/store/draft-store";

const mk = (id: string, meetings: { day: number; periods: string[] }[]): CourseOffering =>
  ({ offering_id: id, name: { zh: id }, meetings, classes: [], teachers: [] } as unknown as CourseOffering);

const A = mk("A", [{ day: 1, periods: ["3", "4"] }]);                          // Mon 3-4
const B = mk("B", [{ day: 1, periods: ["4"] }, { day: 3, periods: ["5"] }]);   // Mon4 + Wed5
const C = mk("C", [{ day: 3, periods: ["5"] }]);                              // Wed5
const D = mk("D", [{ day: 5, periods: ["1"] }]);                              // Fri1，不衝
const E = mk("E", []);                                                        // 無時段

const table: Record<string, CourseOffering> = { A, B, C, D, E };
const byId = (id: string) => table[id];
const placed = (...pairs: [string, number][]): PlacedCourse[] =>
  pairs.map(([offering_id, priority]) => ({ offering_id, priority }));

describe("submitOrder", () => {
  it("無衝堂時只做重編號，順序不變", () => {
    const r = submitOrder(placed(["D", 2], ["E", 7]), byId);
    expect(r.map((o) => o.offeringId)).toEqual(["D", "E"]);
    expect(r.map((o) => o.priority)).toEqual([1, 2]);
    expect(r.every((o) => o.tier === 1)).toBe(true);
  });

  it("遞移衝堂組內只有 priority 最小者是第一志願，其餘落到後段", () => {
    // A,B,C 是一個遞移連通分量；D 不衝
    const r = submitOrder(placed(["A", 1], ["B", 2], ["C", 3], ["D", 4]), byId);
    expect(r.map((o) => o.offeringId)).toEqual(["A", "D", "B", "C"]);
    expect(r.map((o) => o.tier)).toEqual([1, 1, 2, 2]);
    expect(r.map((o) => o.priority)).toEqual([1, 2, 3, 4]);
  });

  it("第一志願段與備選段內各自保持排課站的 priority 順序", () => {
    // 讓衝堂組的最小 priority 大於不衝課程，驗證 winners 段有重新排序
    const r = submitOrder(placed(["A", 5], ["B", 6], ["D", 1]), byId);
    expect(r.map((o) => o.offeringId)).toEqual(["D", "A", "B"]);
    expect(r.map((o) => o.tier)).toEqual([1, 1, 2]);
  });

  it("priority 有空洞也能正確排序並輸出連續 1..N", () => {
    const r = submitOrder(placed(["D", 10], ["A", 3], ["B", 99]), byId);
    expect(r.map((o) => o.offeringId)).toEqual(["A", "D", "B"]);
    expect(r.map((o) => o.priority)).toEqual([1, 2, 3]);
  });

  it("無時段的課程自成一組，算第一志願", () => {
    const r = submitOrder(placed(["E", 1]), byId);
    expect(r).toEqual([{ offeringId: "E", priority: 1, tier: 1 }]);
  });

  it("空清單回空陣列", () => {
    expect(submitOrder([], byId)).toEqual([]);
  });

  it("catalog 查不到的課號會被剔除，且不留下 priority 空洞", () => {
    const r = submitOrder(placed(["D", 1], ["ZZZ", 2], ["A", 3]), byId);
    expect(r.map((o) => o.offeringId)).toEqual(["D", "A"]);
    expect(r.map((o) => o.priority)).toEqual([1, 2]);
  });
});
