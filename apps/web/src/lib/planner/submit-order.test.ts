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

  it("多個獨立衝堂組：兩段內都各自重排，不只 winners 段", () => {
    // 需要兩個彼此不衝堂、但各自內部衝堂的組。
    // 用既有的 A/B（Mon4 相衝）當一組；另一組要自己建，且與 A/B 都不衝。
    const F = mk("F", [{ day: 2, periods: ["1", "2"] }]);   // Tue 1-2
    const G = mk("G", [{ day: 2, periods: ["2"] }]);        // Tue 2 → 與 F 衝
    const table2: Record<string, CourseOffering> = { A, B, F, G };
    const byId2 = (id: string) => table2[id];

    // priority: A=5 B=9（組一）、F=1 G=7（組二）
    // 組一 winner=A(5) loser=B(9)；組二 winner=F(1) loser=G(7)
    // winners 按 priority 升序 → [F(1), A(5)]
    // losers  按 priority 升序 → [G(7), B(9)]
    // 合併重編 → F(1,t1) A(2,t1) G(3,t2) B(4,t2)
    const r = submitOrder(placed(["A", 5], ["B", 9], ["F", 1], ["G", 7]), byId2);
    expect(r.map((o) => o.offeringId)).toEqual(["F", "A", "G", "B"]);
    expect(r.map((o) => o.tier)).toEqual([1, 1, 2, 2]);
    expect(r.map((o) => o.priority)).toEqual([1, 2, 3, 4]);
  });

  it("meetings 欄位整個缺席（非空陣列）也視為無衝堂", () => {
    const H = { offering_id: "H", name: { zh: "H" } } as unknown as CourseOffering;
    const r = submitOrder(placed(["H", 1]), (id) => (id === "H" ? H : undefined));
    expect(r).toEqual([{ offeringId: "H", priority: 1, tier: 1 }]);
  });
});
