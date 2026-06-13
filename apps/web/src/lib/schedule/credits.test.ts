import { describe, it, expect } from "vitest";
import { creditSummary } from "./credits";
import type { CourseOffering } from "@/lib/data/types";

const mk = (id: string, credits: number | null, meetings: { day: number; periods: string[] }[], isPlaceholder = false): CourseOffering =>
  ({ offering_id: id, name: { zh: id }, credits, meetings, is_placeholder: isPlaceholder, classes: [], teachers: [] } as unknown as CourseOffering);

const A = mk("A", 3, [{ day: 1, periods: ["3"] }]);             // Mon3
const B = mk("B", 2, [{ day: 1, periods: ["3"] }]);             // Mon3 (conflicts with A)
const C = mk("C", 1, [{ day: 5, periods: ["1"] }]);             // Fri1, no conflict
const PH = mk("PH", 0, [{ day: 2, periods: ["1"] }], true);     // placeholder
const HALF = mk("HALF", 0.5, [{ day: 4, periods: ["9"] }]);     // real 0.5-credit
const NULLC = mk("NULL", null, [{ day: 6, periods: ["1"] }]);   // unknown credits

describe("creditSummary", () => {
  const byId = (id: string) => ({ A, B, C, PH, HALF, NULLC }[id]!);

  it("counts first preference per conflict group; A(p1) over B(p2) → 3, plus C(1) = 4", () => {
    const placed = [{ offering_id: "A", priority: 1 }, { offering_id: "B", priority: 2 }, { offering_id: "C", priority: 3 }];
    const s = creditSummary(placed, byId);
    expect(s.firstChoiceCredits).toBe(4);     // 3 (A) + 1 (C); B excluded (loses to A in group)
    expect(s.conflictGroupCount).toBe(1);     // {A,B}
  });

  it("excludes only is_placeholder; real 0.5 counts; null → 0 + unknown count", () => {
    const placed = [{ offering_id: "HALF", priority: 1 }, { offering_id: "PH", priority: 2 }, { offering_id: "NULL", priority: 3 }];
    const s = creditSummary(placed, byId);
    expect(s.firstChoiceCredits).toBe(0.5);   // HALF counts, PH excluded, NULL=0
    expect(s.unknownCreditCount).toBe(1);     // NULL
  });
});
