# Web 排課器 M1-B · Core Logic — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure, fully-unit-tested logic layer the UI sits on: text normalization, search index + "search anything" ranking, structured filters (weekday/period/college/unit/class/EMI with cross-AND/intra-OR), period ordering, conflict detection (connected components), credit computation (first-preference per conflict group, placeholder-excluded), and the `draft-store` (favorites/placed/priority with dedup, reorder, stale recovery).

**Architecture:** Framework-free TypeScript modules under `apps/web/src/lib/{search,schedule,filters}` + one Zustand store. No React, no DOM. Inputs are the generated `CourseOffering`/`PeriodTable` types from M1-A. Every module is deterministic and tested in isolation.

**Tech Stack:** TypeScript, Vitest, Zustand (+ persist middleware). Depends on M1-A (`@/lib/data/types`, Vitest setup).

**Spec:** `docs/superpowers/specs/2026-06-13-web-m1-planner-design.md` §3 (search/filters), §4 (draft model), §5 (conflict/credits). Period tokens: `1,2,3,4,N,5,6,7,8,9,A,B,C,D` (orders 0–13).

---

## File Structure (locked here)

```
apps/web/src/
  lib/search/normalize.ts          # NFKC + lowercase + strip whitespace; bigrams
  lib/search/build-index.ts        # CourseOffering[] -> SearchDoc[] (blob + bigram set + code/name keys)
  lib/search/search.ts             # query + ranking + cap; pure
  lib/filters/types.ts             # FilterState
  lib/filters/emi.ts               # EMI (英文授課) language value-set predicate
  lib/filters/college-map.ts       # unit_code -> 學院 (static), unmapped -> 未分類
  lib/filters/apply.ts             # predicate composition (cross-AND, intra-OR) over CourseOffering[]
  lib/schedule/periods.ts          # PeriodTable -> order/index helpers
  lib/schedule/conflict.ts         # slot map + connected components (union-find)
  lib/schedule/credits.ts          # first-pref-per-group, exclude is_placeholder, null=0
  store/draft-store.ts             # favorites/placed/priority; dedup; reorder; stale recovery
```

---

### Task 1: `normalize` + bigrams

**Files:** Create `apps/web/src/lib/search/normalize.ts`, `normalize.test.ts`

- [ ] **Step 1: Write failing test — `normalize.test.ts`**

```typescript
import { describe, it, expect } from "vitest";
import { normalize, bigrams } from "./normalize";

describe("normalize", () => {
  it("NFKC folds full-width, lowercases, strips whitespace", () => {
    expect(normalize("　資料 結構 ＡＢＣ")).toBe("資料結構abc");
    expect(normalize("Data Structures")).toBe("datastructures");
  });
  it("handles null/empty", () => {
    expect(normalize("")).toBe("");
    expect(normalize(null)).toBe("");
  });
});

describe("bigrams", () => {
  it("produces overlapping 2-grams", () => {
    expect([...bigrams("資料結構")]).toEqual(["資料", "料結", "結構"]);
  });
  it("single char falls back to the unigram", () => {
    expect([...bigrams("林")]).toEqual(["林"]);
  });
  it("empty -> empty set", () => {
    expect(bigrams("").size).toBe(0);
  });
});
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test src/lib/search/normalize.test.ts` → FAIL.

- [ ] **Step 3: Implement `normalize.ts`**

```typescript
/** NFKC (full-width→half-width), lowercase, strip all whitespace. */
export function normalize(s: string | null | undefined): string {
  if (!s) return "";
  return s.normalize("NFKC").toLowerCase().replace(/\s+/g, "");
}

/** Overlapping 2-grams of a normalized string; single-char → the unigram. */
export function bigrams(s: string): Set<string> {
  const out = new Set<string>();
  if (!s) return out;
  if (s.length === 1) { out.add(s); return out; }
  for (let i = 0; i < s.length - 1; i++) out.add(s.slice(i, i + 2));
  return out;
}
```

- [ ] **Step 4: Run to verify pass** → `pnpm test src/lib/search/normalize.test.ts` PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/search/normalize.ts apps/web/src/lib/search/normalize.test.ts
git commit -m "feat(web): search normalize + bigram tokenizer (NFKC/lowercase/strip)"
```

---

### Task 2: `build-index`

**Files:** Create `apps/web/src/lib/search/build-index.ts`, `build-index.test.ts`

- [ ] **Step 1: Write failing test — `build-index.test.ts`**

```typescript
import { describe, it, expect } from "vitest";
import { buildIndex } from "./build-index";
import type { CourseOffering } from "@/lib/data/types";

const course = {
  offering_id: "360712", course_code: "2B05003",
  name: { zh: "資料結構", en: "Data Structures" },
  teachers: [{ code: "1", name: "王老師" }],
  unit_code: "59", unit_name: "資工", notes_raw: "限資工系",
  classes: [{ code: "2652", name: "資工五", kind: "regular" }],
} as unknown as CourseOffering;

describe("buildIndex", () => {
  it("creates one SearchDoc per course with normalized blob + keys", () => {
    const docs = buildIndex([course]);
    expect(docs).toHaveLength(1);
    const d = docs[0];
    expect(d.offeringId).toBe("360712");
    expect(d.codeKeys).toContain("360712");
    expect(d.codeKeys).toContain("2b05003");
    expect(d.nameKey).toBe("資料結構");
    expect(d.blob).toContain("資料結構");
    expect(d.blob).toContain("datastructures");
    expect(d.blob).toContain("王老師");
    expect(d.blob).toContain("資工");
    expect(d.bigrams.has("資料")).toBe(true);
  });
});
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `build-index.ts`**

```typescript
import type { CourseOffering } from "@/lib/data/types";
import { normalize, bigrams } from "./normalize";

export interface SearchDoc {
  offeringId: string;
  codeKeys: string[];   // normalized offering_id + course_code (for exact/prefix)
  nameKey: string;      // normalized zh name (for exact/prefix)
  blob: string;         // normalized concat of all searchable fields
  bigrams: Set<string>; // bigrams of blob
}

export function buildIndex(courses: CourseOffering[]): SearchDoc[] {
  return courses.map((c) => {
    const parts = [
      c.name?.zh, c.name?.en,
      ...(c.teachers ?? []).map((t) => t.name),
      c.offering_id, c.course_code ?? "",
      c.unit_name ?? "", c.unit_code ?? "",
      ...(c.classes ?? []).map((k) => k.name),
      c.notes_raw ?? "",
    ];
    const blob = parts.map(normalize).join("|");
    const codeKeys = [normalize(c.offering_id), normalize(c.course_code)].filter(Boolean);
    return {
      offeringId: c.offering_id,
      codeKeys,
      nameKey: normalize(c.name?.zh),
      blob,
      bigrams: bigrams(blob.replace(/\|/g, "")),
    };
  });
}
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/search/build-index.ts apps/web/src/lib/search/build-index.test.ts
git commit -m "feat(web): search index builder (search-anything blob + code/name keys + bigrams)"
```

---

### Task 3: `search` (ranking + cap)

**Files:** Create `apps/web/src/lib/search/search.ts`, `search.test.ts`

- [ ] **Step 1: Write failing test — `search.test.ts`**

```typescript
import { describe, it, expect } from "vitest";
import { search } from "./search";
import type { SearchDoc } from "./build-index";

function doc(offeringId: string, name: string, code: string, blobExtra = ""): SearchDoc {
  const blob = (name + code + blobExtra).normalize("NFKC").toLowerCase().replace(/\s+/g, "");
  const bg = new Set<string>();
  for (let i = 0; i < blob.length - 1; i++) bg.add(blob.slice(i, i + 2));
  return { offeringId, codeKeys: [code.toLowerCase()], nameKey: name.toLowerCase(), blob, bigrams: bg };
}

const docs: SearchDoc[] = [
  doc("360712", "資料結構", "2b05003", "王老師"),
  doc("360820", "演算法", "2b05004", "李老師"),
  doc("360905", "資料庫系統", "2b05010", "陳老師"),
];

describe("search", () => {
  it("exact offering_id ranks first", () => {
    expect(search(docs, "360712")[0].offeringId).toBe("360712");
  });
  it("name substring/bigram finds courses ('資料' → 資料結構 & 資料庫系統)", () => {
    const ids = search(docs, "資料").map((d) => d.offeringId);
    expect(ids).toContain("360712");
    expect(ids).toContain("360905");
    expect(ids).not.toContain("360820");
  });
  it("teacher name is searchable (search anything)", () => {
    expect(search(docs, "李老師").map((d) => d.offeringId)).toEqual(["360820"]);
  });
  it("empty query returns all (capped)", () => {
    expect(search(docs, "  ")).toHaveLength(3);
  });
  it("respects result cap", () => {
    expect(search(docs, "", { limit: 2 })).toHaveLength(2);
  });
});
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `search.ts`**

```typescript
import type { SearchDoc } from "./build-index";
import { normalize, bigrams } from "./normalize";

export interface SearchOptions {
  limit?: number;       // default 200 (spec §3.1)
  signal?: AbortSignal; // cheap honor; search is sync sub-ms
}

interface Scored { doc: SearchDoc; score: number; }

export function search(docs: SearchDoc[], rawQuery: string, opts: SearchOptions = {}): SearchDoc[] {
  const limit = opts.limit ?? 200;
  if (opts.signal?.aborted) return [];
  const q = normalize(rawQuery);
  if (!q) return docs.slice(0, limit);

  const qbg = bigrams(q);
  const scored: Scored[] = [];
  for (const doc of docs) {
    let score = 0;
    if (doc.codeKeys.includes(q)) score = 1000;                       // exact code
    else if (doc.codeKeys.some((k) => k.startsWith(q))) score = 500;  // code prefix
    else if (doc.nameKey === q) score = 400;                          // name exact
    else if (doc.nameKey.startsWith(q)) score = 300;                  // name prefix
    else {
      // bigram overlap (CJK) scaled to query size + substring bonus
      let shared = 0;
      for (const b of qbg) if (doc.bigrams.has(b)) shared++;
      if (qbg.size > 0) score = Math.round((shared / qbg.size) * 200);
      if (doc.blob.includes(q)) score += 50;
    }
    if (score > 0) scored.push({ doc, score });
  }
  scored.sort((a, b) =>
    b.score - a.score || a.doc.offeringId.localeCompare(b.doc.offeringId), // tie-break: offering_id asc
  );
  return scored.slice(0, limit).map((s) => s.doc);
}
```

- [ ] **Step 4: Run → PASS (5 tests).**

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/search/search.ts apps/web/src/lib/search/search.test.ts
git commit -m "feat(web): search ranking (exact-code>prefix>name>bigram>tie-break) + result cap"
```

---

### Task 4: EMI predicate + filter types

**Files:** Create `apps/web/src/lib/filters/types.ts`, `lib/filters/emi.ts`, `emi.test.ts`

- [ ] **Step 1: Write failing test — `emi.test.ts`**

```typescript
import { describe, it, expect } from "vitest";
import { isEmi } from "./emi";

describe("isEmi", () => {
  it("treats English/EMI markers as EMI", () => {
    expect(isEmi("英文授課")).toBe(true);
    expect(isEmi("全英語")).toBe(true);
    expect(isEmi("English")).toBe(true);
    expect(isEmi("中英")).toBe(true);
    expect(isEmi("EMI")).toBe(true);
  });
  it("non-English / null → not EMI", () => {
    expect(isEmi("中文")).toBe(false);
    expect(isEmi(null)).toBe(false);
    expect(isEmi("")).toBe(false);
  });
});
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `emi.ts`**

```typescript
// 英文授課/EMI raw-value whitelist (spec §3.2). language is free text from source;
// match on substrings. Tune per-term as new values appear.
const EMI_MARKERS = ["英", "english", "emi"];

export function isEmi(language: string | null | undefined): boolean {
  if (!language) return false;
  const v = language.toLowerCase();
  return EMI_MARKERS.some((m) => v.includes(m));
}
```

- [ ] **Step 4: Write `types.ts`**

```typescript
// Cross-category AND, intra-category OR (spec §3.2).
export interface FilterState {
  weekdays: number[];   // 1..7 (ISO: Mon=1)
  periods: string[];    // period tokens "1".."9","N","A".."D"
  colleges: string[];   // 學院 names (via college-map)
  units: string[];      // unit_code
  classes: string[];    // class code
  emiOnly: boolean;
}

export const EMPTY_FILTER: FilterState = {
  weekdays: [], periods: [], colleges: [], units: [], classes: [], emiOnly: false,
};
```

- [ ] **Step 5: Run → `pnpm test src/lib/filters/emi.test.ts` PASS.**

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/filters/types.ts apps/web/src/lib/filters/emi.ts apps/web/src/lib/filters/emi.test.ts
git commit -m "feat(web): filter state types + EMI(英文授課) predicate"
```

---

### Task 5: `college-map` (unit_code → 學院)

**Files:** Create `apps/web/src/lib/filters/college-map.ts`, `college-map.test.ts`

- [ ] **Step 1: Write failing test — `college-map.test.ts`**

```typescript
import { describe, it, expect } from "vitest";
import { collegeOf, UNCLASSIFIED } from "./college-map";

describe("collegeOf", () => {
  it("maps known unit codes to their college", () => {
    expect(collegeOf("30")).toBe("機電學院");   // 機械
    expect(collegeOf("59")).toBe("電資學院");   // 資工
    expect(collegeOf("37")).toBe("管理學院");   // 工管
    expect(collegeOf("38")).toBe("設計學院");   // 工設
  });
  it("unmapped unit code → 未分類 (no throw, no dropped course)", () => {
    expect(collegeOf("ZZ")).toBe(UNCLASSIFIED);
    expect(collegeOf(null)).toBe(UNCLASSIFIED);
  });
});
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `college-map.ts`**

> Source: NTUT unit codes from `docs/DESIGN.md` §1.3 + course-system `unit` table. Static, hand-curated, re-verified per term. Unmapped → `未分類` (never drop a course).

```typescript
export const UNCLASSIFIED = "未分類";

// unit_code → 學院. Curated from DESIGN §1.3 unit table (北科 ~7 colleges).
// Codes seen: 01 教務處, 05 進修部, 10 體育室, 14 通識中心, 2B 智動科, 30 機械,
// 31 電機, 32 化工, 34 土木, 36 電子, 37 工管, 38 工設, 39 建築, 54 應英,
// 59 資工, 91 學程, AA 校院級, AB 資財, AC 互動設計 …
const MAP: Record<string, string> = {
  "30": "機電學院", "2B": "機電學院", "33": "機電學院",         // 機械/智動/車輛
  "31": "電資學院", "36": "電資學院", "59": "電資學院", "61": "電資學院", // 電機/電子/資工/光電
  "32": "工程學院", "34": "工程學院", "35": "工程學院",         // 化工/土木/分子
  "37": "管理學院", "AB": "管理學院", "40": "管理學院", "41": "管理學院", // 工管/資財/企管/資管
  "38": "設計學院", "39": "設計學院", "AC": "設計學院",         // 工設/建築/互動
  "54": "人文與社會科學學院", "14": "人文與社會科學學院", "10": "人文與社會科學學院", // 應英/通識/體育
};

export function collegeOf(unitCode: string | null | undefined): string {
  if (!unitCode) return UNCLASSIFIED;
  return MAP[unitCode] ?? UNCLASSIFIED;
}

export function allColleges(): string[] {
  return [...new Set(Object.values(MAP)), UNCLASSIFIED];
}
```

- [ ] **Step 4: Run → PASS.** (If a code in the test isn't in DESIGN, adjust the test to a code that is — but 30/59/37/38 are confirmed in DESIGN §1.3.)

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/filters/college-map.ts apps/web/src/lib/filters/college-map.test.ts
git commit -m "feat(web): unit_code→學院 static map (unmapped→未分類)"
```

---

### Task 6: `apply` filters (cross-AND, intra-OR)

**Files:** Create `apps/web/src/lib/filters/apply.ts`, `apply.test.ts`

- [ ] **Step 1: Write failing test — `apply.test.ts`**

```typescript
import { describe, it, expect } from "vitest";
import { applyFilters } from "./apply";
import { EMPTY_FILTER } from "./types";
import type { CourseOffering } from "@/lib/data/types";

const mk = (o: Partial<CourseOffering>): CourseOffering => ({
  offering_id: "x", name: { zh: "課" }, meetings: [], classes: [], teachers: [],
  ...o,
} as unknown as CourseOffering);

const monP3 = mk({ offering_id: "a", unit_code: "59", language: "中文",
  meetings: [{ day: 1, periods: ["3", "4"] }] as never, classes: [{ code: "2652", name: "資工五", kind: "regular" }] as never });
const wedP5 = mk({ offering_id: "b", unit_code: "37", language: "英文授課",
  meetings: [{ day: 3, periods: ["5"] }] as never, classes: [{ code: "9999", name: "工管三", kind: "regular" }] as never });

describe("applyFilters", () => {
  it("empty filter passes everything", () => {
    expect(applyFilters([monP3, wedP5], EMPTY_FILTER)).toHaveLength(2);
  });
  it("intra-category OR: weekdays [1,3] keeps both", () => {
    expect(applyFilters([monP3, wedP5], { ...EMPTY_FILTER, weekdays: [1, 3] })).toHaveLength(2);
  });
  it("cross-category AND: weekday=1 AND unit=59 keeps only a", () => {
    const r = applyFilters([monP3, wedP5], { ...EMPTY_FILTER, weekdays: [1], units: ["59"] });
    expect(r.map((c) => c.offering_id)).toEqual(["a"]);
  });
  it("period filter matches any meeting period", () => {
    expect(applyFilters([monP3, wedP5], { ...EMPTY_FILTER, periods: ["5"] }).map((c) => c.offering_id)).toEqual(["b"]);
  });
  it("emiOnly keeps only English-taught", () => {
    expect(applyFilters([monP3, wedP5], { ...EMPTY_FILTER, emiOnly: true }).map((c) => c.offering_id)).toEqual(["b"]);
  });
  it("class filter matches by class code", () => {
    expect(applyFilters([monP3, wedP5], { ...EMPTY_FILTER, classes: ["2652"] }).map((c) => c.offering_id)).toEqual(["a"]);
  });
});
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `apply.ts`**

```typescript
import type { CourseOffering } from "@/lib/data/types";
import type { FilterState } from "./types";
import { isEmi } from "./emi";
import { collegeOf } from "./college-map";

// Each active category is an AND clause; within a category, OR over its values.
export function applyFilters(courses: CourseOffering[], f: FilterState): CourseOffering[] {
  return courses.filter((c) => {
    if (f.weekdays.length && !c.meetings.some((m) => f.weekdays.includes(m.day))) return false;
    if (f.periods.length && !c.meetings.some((m) => m.periods.some((p) => f.periods.includes(p)))) return false;
    if (f.units.length && !(c.unit_code && f.units.includes(c.unit_code))) return false;
    if (f.colleges.length && !f.colleges.includes(collegeOf(c.unit_code))) return false;
    if (f.classes.length && !c.classes.some((k) => f.classes.includes(k.code))) return false;
    if (f.emiOnly && !isEmi(c.language)) return false;
    return true;
  });
}
```

- [ ] **Step 4: Run → PASS (6 tests).**

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/filters/apply.ts apps/web/src/lib/filters/apply.test.ts
git commit -m "feat(web): structured filters (cross-AND, intra-OR) over weekday/period/college/unit/class/EMI"
```

---

### Task 7: `periods` ordering helpers

**Files:** Create `apps/web/src/lib/schedule/periods.ts`, `periods.test.ts`

- [ ] **Step 1: Write failing test — `periods.test.ts`**

```typescript
import { describe, it, expect } from "vitest";
import { periodOrder, sortPeriods, periodLabel } from "./periods";
import type { PeriodTable } from "@/lib/data/types";

const table: PeriodTable = {
  schema_version: 1, timezone: "Asia/Taipei",
  periods: [
    { token: "1", order: 0, start_hm: "08:10", end_hm: "09:00", label: "1" },
    { token: "N", order: 4, start_hm: "12:10", end_hm: "13:00", label: "N" },
    { token: "5", order: 5, start_hm: "13:10", end_hm: "14:00", label: "5" },
    { token: "A", order: 10, start_hm: "18:30", end_hm: "19:20", label: "A" },
  ],
} as PeriodTable;

describe("periods", () => {
  it("periodOrder maps token → order (N before 5, A after 9)", () => {
    const ord = periodOrder(table);
    expect(ord.get("N")).toBe(4);
    expect(ord.get("5")).toBe(5);
    expect(ord.get("A")).toBe(10);
  });
  it("sortPeriods uses the non-1..14 ordering", () => {
    expect(sortPeriods(["5", "N", "1"], table)).toEqual(["1", "N", "5"]);
  });
  it("periodLabel returns display label", () => {
    expect(periodLabel("N", table)).toBe("N");
  });
});
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `periods.ts`**

```typescript
import type { PeriodTable } from "@/lib/data/types";

export function periodOrder(table: PeriodTable): Map<string, number> {
  return new Map(table.periods.map((p) => [p.token, p.order]));
}

export function sortPeriods(tokens: string[], table: PeriodTable): string[] {
  const ord = periodOrder(table);
  return [...tokens].sort((a, b) => (ord.get(a) ?? 99) - (ord.get(b) ?? 99));
}

export function periodLabel(token: string, table: PeriodTable): string {
  return table.periods.find((p) => p.token === token)?.label ?? token;
}

/** Period tokens in display order (for grid rows). */
export function orderedPeriodTokens(table: PeriodTable): string[] {
  return [...table.periods].sort((a, b) => a.order - b.order).map((p) => p.token);
}
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/schedule/periods.ts apps/web/src/lib/schedule/periods.test.ts
git commit -m "feat(web): period ordering helpers (N/A-D non-1..14 model)"
```

---

### Task 8: `conflict` (slot map + connected components)

**Files:** Create `apps/web/src/lib/schedule/conflict.ts`, `conflict.test.ts`

- [ ] **Step 1: Write failing test — `conflict.test.ts`**

```typescript
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
    const m = slotMap([A, B], (id) => ({ A, B }[id]!));
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
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `conflict.ts`**

```typescript
import type { CourseOffering } from "@/lib/data/types";

export const slotKey = (day: number, period: string): string => `${day}-${period}`;

/** day-period slot → offering_ids occupying it. */
export function slotMap(
  courses: CourseOffering[],
  _byId?: unknown,
): Map<string, string[]> {
  const m = new Map<string, string[]>();
  for (const c of courses) {
    for (const mt of c.meetings ?? []) {
      for (const p of mt.periods) {
        const k = slotKey(mt.day, p);
        (m.get(k) ?? m.set(k, []).get(k)!).push(c.offering_id);
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
    let c = x; while (parent.get(c) !== r) { const n = parent.get(c)!; parent.set(c, r); c = n; }
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
        const arr = bySlot.get(k) ?? [];
        arr.push(id); bySlot.set(k, arr);
      }
    }
  }
  for (const ids of bySlot.values()) {
    for (let i = 1; i < ids.length; i++) union(ids[0], ids[i]);
  }

  const comps = new Map<string, string[]>();
  for (const id of offeringIds) {
    const root = find(id);
    (comps.get(root) ?? comps.set(root, []).get(root)!).push(id);
  }
  return [...comps.values()];
}

/** Slot keys that hold >1 course (for orange/red cell coloring). */
export function conflictedSlots(courses: CourseOffering[]): Set<string> {
  const out = new Set<string>();
  for (const [k, ids] of slotMap(courses)) if (ids.length > 1) out.add(k);
  return out;
}
```

- [ ] **Step 4: Run → PASS (3 tests).**

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/schedule/conflict.ts apps/web/src/lib/schedule/conflict.test.ts
git commit -m "feat(web): conflict detection (slot map + transitive connected components, day×period only)"
```

---

### Task 9: `credits` (first-pref per group, exclude placeholder)

**Files:** Create `apps/web/src/lib/schedule/credits.ts`, `credits.test.ts`

- [ ] **Step 1: Write failing test — `credits.test.ts`**

```typescript
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
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `credits.ts`**

```typescript
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
```

- [ ] **Step 4: Run → PASS (2 tests).**

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/schedule/credits.ts apps/web/src/lib/schedule/credits.test.ts
git commit -m "feat(web): credit summary (first-pref per conflict group, exclude is_placeholder, null=0)"
```

---

### Task 10: `draft-store` (favorites/placed/priority; dedup; reorder; stale recovery)

**Files:** Create `apps/web/src/store/draft-store.ts`, `draft-store.test.ts`

- [ ] **Step 1: Write failing test — `draft-store.test.ts`**

```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { useDraftStore } from "./draft-store";

describe("draft-store", () => {
  beforeEach(() => useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] }));

  it("place assigns next priority and dedups", () => {
    const s = useDraftStore.getState();
    s.place("A"); s.place("B"); s.place("A"); // A twice
    const p = useDraftStore.getState().placed;
    expect(p.map((x) => x.offering_id)).toEqual(["A", "B"]);
    expect(p.find((x) => x.offering_id === "A")!.priority).toBe(1);
    expect(p.find((x) => x.offering_id === "B")!.priority).toBe(2);
  });

  it("favorite toggles independently of placed and dedups", () => {
    const s = useDraftStore.getState();
    s.toggleFavorite("A"); s.toggleFavorite("A"); s.toggleFavorite("B");
    expect(useDraftStore.getState().favorites).toEqual(["B"]);
  });

  it("reorder within a group swaps priorities", () => {
    const s = useDraftStore.getState();
    s.place("A"); s.place("B"); // A=1, B=2
    s.setPriority("B", 1); s.setPriority("A", 2);
    const byId = (id: string) => useDraftStore.getState().placed.find((p) => p.offering_id === id)!;
    expect(byId("B").priority).toBe(1);
    expect(byId("A").priority).toBe(2);
  });

  it("reconcile drops placed/favorites whose offering_id no longer exists; returns dropped ids", () => {
    const s = useDraftStore.getState();
    s.place("A"); s.place("GONE"); s.toggleFavorite("ALSO_GONE");
    const dropped = s.reconcile(new Set(["A"]));
    expect(dropped.sort()).toEqual(["ALSO_GONE", "GONE"]);
    expect(useDraftStore.getState().placed.map((p) => p.offering_id)).toEqual(["A"]);
    expect(useDraftStore.getState().favorites).toEqual([]);
  });
});
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `draft-store.ts`**

```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface PlacedCourse { offering_id: string; priority: number; }

interface DraftState {
  schema_version: number;
  termKey: string;
  favorites: string[];
  placed: PlacedCourse[];
  setTerm: (termKey: string) => void;
  place: (offeringId: string) => void;
  unplace: (offeringId: string) => void;
  setPriority: (offeringId: string, priority: number) => void;
  toggleFavorite: (offeringId: string) => void;
  /** Drop placed/favorites not in validIds; returns dropped ids (spec §4 stale recovery). */
  reconcile: (validIds: Set<string>) => string[];
}

const DRAFT_SCHEMA = 1;

export const useDraftStore = create<DraftState>()(
  persist(
    (set, get) => ({
      schema_version: DRAFT_SCHEMA,
      termKey: "",
      favorites: [],
      placed: [],

      setTerm: (termKey) => set({ termKey }),

      place: (offeringId) => set((s) => {
        if (s.placed.some((p) => p.offering_id === offeringId)) return s; // dedup
        const maxPrio = s.placed.reduce((m, p) => Math.max(m, p.priority), 0);
        return { placed: [...s.placed, { offering_id: offeringId, priority: maxPrio + 1 }] };
      }),

      unplace: (offeringId) => set((s) => ({
        placed: s.placed.filter((p) => p.offering_id !== offeringId), // gaps allowed (spec §4)
      })),

      setPriority: (offeringId, priority) => set((s) => ({
        placed: s.placed.map((p) => (p.offering_id === offeringId ? { ...p, priority } : p)),
      })),

      toggleFavorite: (offeringId) => set((s) => ({
        favorites: s.favorites.includes(offeringId)
          ? s.favorites.filter((x) => x !== offeringId)
          : [...s.favorites, offeringId],
      })),

      reconcile: (validIds) => {
        const s = get();
        const dropped = [
          ...s.placed.map((p) => p.offering_id).filter((id) => !validIds.has(id)),
          ...s.favorites.filter((id) => !validIds.has(id)),
        ];
        if (dropped.length) {
          set({
            placed: s.placed.filter((p) => validIds.has(p.offering_id)),
            favorites: s.favorites.filter((id) => validIds.has(id)),
          });
        }
        return dropped;
      },
    }),
    {
      name: "ntutbox-draft",
      // one persisted blob per term: partition by termKey in the storage key.
      partialize: (s) => ({ schema_version: s.schema_version, termKey: s.termKey, favorites: s.favorites, placed: s.placed }),
    },
  ),
);
```

> Note (for M1-C): per-term isolation is done by calling `useDraftStore.persist.setOptions({ name: \`ntutbox-draft-${termKey}\` })` then `rehydrate()` when the term changes. M1-B ships the single-store logic + tests; M1-C wires per-term keying. The `reconcile()` call happens after a term loads.

- [ ] **Step 4: Run → PASS (4 tests).**

- [ ] **Step 5: Run full M1-B suite + typecheck**

Run: `cd apps/web && pnpm test && pnpm typecheck`
Expected: all logic tests pass, no type errors.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/store/draft-store.ts apps/web/src/store/draft-store.test.ts
git commit -m "feat(web): draft-store (favorites/placed/priority, dedup, reorder, stale reconcile)"
```

---

## Self-Review (M1-B)

**Spec coverage:**
- §3.1 normalize + bigram + index + ranking (exact-code>prefix>name>bigram>tie-break) + cap → Tasks 1,2,3. ✓ (`signal` honored cheaply in Task 3; search is sync sub-ms — cancellation handled by UI in M1-C, noted.)
- §3.2 filters cross-AND/intra-OR + EMI value set + class pool labels(data via `kind`, UI in M1-C) + college unmapped→未分類 → Tasks 4,5,6. ✓
- §5.1 conflict day×period + connected components (transitive) → Task 8. ✓
- §5.3 credits first-pref per group, exclude is_placeholder only, real 0.5 counts, null=0 → Task 9. ✓
- §5.4 (multi-section/no-time handled at UI/credits: no-time courses simply contribute no slots → never conflict, still counted) → Task 8/9 behavior. ✓
- §4 draft model snake_case fields, dedup, gaps-allowed, reorder, stale reconcile → Task 10. ✓

**Placeholder scan:** none — full code in every step.

**Type consistency:** `SearchDoc` (Task 2) consumed unchanged in Task 3. `PlacedRef`/`PlacedCourse` both `{ offering_id, priority }`. `conflictGroups(ids, byId)` signature identical in Task 8 def and Task 9 use. `creditSummary(placed, byId)` matches test. `collegeOf` used by `applyFilters` (Task 6) matches Task 5 export. Period token type matches generated `PeriodRef.token`.

**Deviation flagged:** spec §3.1 mentioned `search()` AbortSignal for term-switch cancel; implemented as a cheap `signal?.aborted` early-return since search is synchronous. Term-switch invalidation is actually handled by index rebuild + UI generation token (M1-C). No functional gap.
