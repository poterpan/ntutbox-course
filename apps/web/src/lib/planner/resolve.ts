import type { CourseOffering } from "@/lib/data/types";
import type { PlacedCourse } from "@/store/draft-store";

export function occupantsForSlot(
  placed: PlacedCourse[],
  byId: (id: string) => CourseOffering | undefined,
  day: number,
  period: string,
): string[] {
  const prio = new Map(placed.map((p) => [p.offering_id, p.priority]));
  return placed
    .filter((p) => (byId(p.offering_id)?.meetings ?? []).some((m) => m.day === day && (m.periods as string[]).includes(period)))
    .map((p) => p.offering_id)
    .sort((a, b) => (prio.get(a) ?? 0) - (prio.get(b) ?? 0));
}

export function firstChoiceId(ids: string[], prio: Map<string, number>): string | undefined {
  return [...ids].sort((a, b) => (prio.get(a) ?? 0) - (prio.get(b) ?? 0))[0];
}
