import type { CourseOffering } from "@/lib/data/types";

export const slotKey = (day: number, period: string): string => `${day}-${period}`;

/** day-period slot → offering_ids occupying it. */
export function slotMap(courses: CourseOffering[]): Map<string, string[]> {
  const m = new Map<string, string[]>();
  for (const c of courses) {
    for (const mt of c.meetings ?? []) {
      for (const p of mt.periods) {
        const k = slotKey(mt.day, p);
        const arr = m.get(k);
        if (arr) {
          arr.push(c.offering_id);
        } else {
          m.set(k, [c.offering_id]);
        }
      }
    }
  }
  return m;
}

/** Connected components over offering ids: edge if two courses share any slot (transitive). */
export function conflictGroups(
  offeringIds: string[],
  byId: (id: string) => CourseOffering | undefined,
): string[][] {
  const parent = new Map<string, string>();
  const find = (x: string): string => {
    let r = x;
    while (parent.get(r) !== r) r = parent.get(r)!;
    // path compression
    let c = x;
    while (parent.get(c) !== r) {
      const n = parent.get(c)!;
      parent.set(c, r);
      c = n;
    }
    return r;
  };
  const union = (a: string, b: string) => { parent.set(find(a), find(b)); };

  for (const id of offeringIds) parent.set(id, id);

  // slot → ids, then union all ids sharing a slot
  const bySlot = new Map<string, string[]>();
  for (const id of offeringIds) {
    const c = byId(id);
    for (const mt of c?.meetings ?? []) {
      for (const p of mt.periods) {
        const k = slotKey(mt.day, p);
        const arr = bySlot.get(k);
        if (arr) {
          arr.push(id);
        } else {
          bySlot.set(k, [id]);
        }
      }
    }
  }
  for (const ids of bySlot.values()) {
    for (let i = 1; i < ids.length; i++) union(ids[0], ids[i]);
  }

  const comps = new Map<string, string[]>();
  for (const id of offeringIds) {
    const root = find(id);
    const arr = comps.get(root);
    if (arr) {
      arr.push(id);
    } else {
      comps.set(root, [id]);
    }
  }
  return [...comps.values()];
}

/** Slot keys that hold >1 course (for orange/red cell coloring). */
export function conflictedSlots(courses: CourseOffering[]): Set<string> {
  const out = new Set<string>();
  for (const [k, ids] of slotMap(courses)) if (ids.length > 1) out.add(k);
  return out;
}
