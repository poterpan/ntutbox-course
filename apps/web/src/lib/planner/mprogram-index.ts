import type { MicroProgram, MicroProgramDirectory } from "@/lib/data/types";

// offering_id → 該課號所屬的所有微學程。用於課程詳情/搜尋結果標示「屬於哪些微學程」。
export function buildProgramIndex(dir: MicroProgramDirectory | null): Map<string, MicroProgram[]> {
  const m = new Map<string, MicroProgram[]>();
  for (const p of dir?.programs ?? [])
    for (const oid of p.offering_ids ?? []) {
      const arr = m.get(oid);
      if (arr) arr.push(p);
      else m.set(oid, [p]);
    }
  return m;
}
