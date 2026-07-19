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

const EMPTY_OID_SET: ReadonlySet<string> = new Set();
const oidSetCache = new WeakMap<MicroProgramDirectory, ReadonlySet<string>>();

// 全微學程 offering_id 聯集（與詳情頁 chips 同源）——課程庫「微學程」badge 與三態篩選的判準。
// WeakMap memo 綁 dir 參照：同一份目錄只算一次，供列表容器共用、避免 per-row / per-render 重建。
// 判準刻意用 mprograms.json 的 offering_ids，不用 catalog 的 interdisciplinary 欄位（後者混入非微學程課）。
export function getProgramOidSet(dir: MicroProgramDirectory | null): ReadonlySet<string> {
  if (!dir) return EMPTY_OID_SET;
  const hit = oidSetCache.get(dir);
  if (hit) return hit;
  const s = new Set<string>();
  for (const p of dir.programs ?? []) for (const oid of p.offering_ids ?? []) s.add(oid);
  oidSetCache.set(dir, s);
  return s;
}
