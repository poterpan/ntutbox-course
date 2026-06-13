import type { CourseOffering } from "@/lib/data/types";
import { conflictGroups } from "./conflict";

export interface PlacedRef { offering_id: string; priority: number; }

export interface CreditSummary {
  firstChoiceCredits: number;  // per conflict-group first preference, placeholder-excluded
  placedCredits: number;       // all placed, placeholder-excluded (reference)
  unknownCreditCount: number;  // courses with credits == null
  conflictGroupCount: number;  // groups with >1 course
}

const realCredits = (c: CourseOffering | undefined): number => {
  if (!c || c.is_placeholder) return 0;     // exclude placeholder only
  return typeof c.credits === "number" ? c.credits : 0; // null/unknown → 0
};

export function creditSummary(placed: PlacedRef[], byId: (id: string) => CourseOffering | undefined): CreditSummary {
  const ids = placed.map((p) => p.offering_id);
  const prio = new Map(placed.map((p) => [p.offering_id, p.priority]));
  const groups = conflictGroups(ids, byId);

  let firstChoiceCredits = 0;
  let conflictGroupCount = 0;
  for (const g of groups) {
    if (g.length > 1) conflictGroupCount++;
    const first = [...g].sort((a, b) => (prio.get(a) ?? 0) - (prio.get(b) ?? 0))[0];
    firstChoiceCredits += realCredits(byId(first));
  }

  const placedCredits = ids.reduce((sum, id) => sum + realCredits(byId(id)), 0);
  const unknownCreditCount = ids.filter((id) => byId(id)?.credits == null).length;

  return { firstChoiceCredits, placedCredits, unknownCreditCount, conflictGroupCount };
}
