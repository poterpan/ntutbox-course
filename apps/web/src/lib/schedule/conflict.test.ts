import { describe, it, expect } from "vitest";
import { slotKey, slotMap, conflictGroups } from "./conflict";
import type { CourseOffering } from "@/lib/data/types";

const mk = (id: string, meetings: { day: number; periods: string[] }[]): CourseOffering =>
  ({ offering_id: id, name: { zh: id }, meetings, classes: [], teachers: [] } as unknown as CourseOffering);

const A = mk("A", [{ day: 1, periods: ["3", "4"] }]);                 // Mon 3-4
const B = mk("B", [{ day: 1, periods: ["4"] }, { day: 3, periods: ["5"] }]); // Mon4 + Wed5
const C = mk("C", [{ day: 3, periods: ["5"] }]);                     // Wed5
const D = mk("D", [{ day: 5, periods: ["1"] }]);                     // Fri1 (no conflict)

describe("conflict", () => {
  it("slotKey is day-period", () => expect(slotKey(1, "4")).toBe("1-4"));

  it("slotMap groups placed courses by slot", () => {
    const m = slotMap([A, B]);
    expect(m.get("1-4")?.sort()).toEqual(["A", "B"]); // both at Mon 4
    expect(m.get("1-3")).toEqual(["A"]);
  });

  it("conflictGroups: A-B (Mon4) and B-C (Wed5) form one transitive component {A,B,C}; D alone", () => {
    const byId = (id: string) => ({ A, B, C, D }[id]!);
    const groups = conflictGroups(["A", "B", "C", "D"], byId);
    const comp = groups.find((g) => g.includes("B"))!.sort();
    expect(comp).toEqual(["A", "B", "C"]);
    expect(groups.find((g) => g.includes("D"))).toEqual(["D"]);
  });
});
