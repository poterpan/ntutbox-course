import { describe, it, expect } from "vitest";
import { occupantsForSlot, firstChoiceId } from "./resolve";
import type { CourseOffering } from "@/lib/data/types";

const mk = (id: string, day: number, periods: string[]): CourseOffering =>
  ({ offering_id: id, name: { zh: id }, meetings: [{ day, periods }], classes: [], teachers: [] } as unknown as CourseOffering);

const byId = (id: string) => ({ A: mk("A", 1, ["3", "4"]), B: mk("B", 1, ["4"]) }[id]);

describe("resolve", () => {
  it("occupantsForSlot lists placed ids at (day,period) ordered by priority", () => {
    const placed = [{ offering_id: "B", priority: 2 }, { offering_id: "A", priority: 1 }];
    expect(occupantsForSlot(placed, byId, 1, "4")).toEqual(["A", "B"]); // A(p1) before B(p2)
    expect(occupantsForSlot(placed, byId, 1, "3")).toEqual(["A"]);
  });
  it("firstChoiceId returns the min-priority id", () => {
    expect(firstChoiceId(["B", "A"], new Map([["A", 1], ["B", 2]]))).toBe("A");
  });
});
