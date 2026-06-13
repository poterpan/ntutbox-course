# Web 排課器 M1-A · Foundation & Data Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `apps/web` Next.js (static-export) app with the Liquid-Glass design-system base, generated TS types from the Pydantic data contract, dev fixtures, a swappable `DataSource`, and a `term-store` that loads one term — ending in a page that boots, loads 115-1, and shows course count + catalog/enrollment timestamps.

**Architecture:** Pure client SPA (`output: 'export'`) deployed to Cloudflare Pages. No backend. Data fetched client-side via a `DataSource` abstraction (local fixtures in dev, CDN in prod, chosen by env). Types are generated from `crawler/models.py` so web/crawler never drift. State held in Zustand stores.

**Tech Stack:** Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + framer-motion + Zustand; Vitest + React Testing Library; pnpm. Type gen: Pydantic `model_json_schema()` → `json-schema-to-typescript`.

**Spec:** `docs/superpowers/specs/2026-06-13-web-m1-planner-design.md` (§1, §2, §8). Data roots in `crawler/models.py`: `TermCatalog`, `PeriodTable`, `ClassDirectory`, `EnrollmentLatest`, `Manifest`, `CourseOffering`.

---

## File Structure (locked here)

```
apps/web/
  package.json, tsconfig.json, next.config.ts, vitest.config.ts, vitest.setup.ts
  postcss.config.mjs, components.json (shadcn)
  public/data/v1/                      # dev fixtures (manifest.json + terms/115-1, 114-2)
  src/
    app/layout.tsx                     # root: theme provider, system font, globals
    app/page.tsx                       # M1-A smoke page (load 115-1, show counts/timestamps)
    app/globals.css                    # Tailwind + Liquid-Glass tokens
    components/glass/{GlassPanel,GlassCard,GlassBar}.tsx
    components/ui/                     # shadcn output (button, etc.)
    lib/data/{types.ts,datasource.ts,local-datasource.ts,cdn-datasource.ts,index.ts}
    lib/env.ts                         # NEXT_PUBLIC_DATA_BASE_URL resolution
    store/term-store.ts                # Zustand: load term, generation token, error states
    schema/index.d.ts                  # GENERATED (re-exported by lib/data/types.ts)
packages/schema/
  generate.py                          # dump combined JSON schema from models.py
  package.json                         # "generate" script → json-schema-to-typescript
  schema.json (generated), index.d.ts (generated)
```

**Branch:** Execute on a feature branch `feat/web-m1` (a concurrent session commits infra to `main`; isolate web work, merge when M1-A/B/C land). Create it before Task 1: `git checkout -b feat/web-m1`.

---

### Task 1: Scaffold Next.js static-export app + Vitest

**Files:**
- Create: `apps/web/package.json`, `tsconfig.json`, `next.config.ts`, `vitest.config.ts`, `vitest.setup.ts`, `src/app/layout.tsx`, `src/app/page.tsx`, `src/app/globals.css`

- [ ] **Step 1: Scaffold with create-next-app (non-interactive)**

Run from repo root:
```bash
cd apps/web 2>/dev/null && rm -f README.md; cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course
pnpm create next-app@latest apps/web --ts --tailwind --app --src-dir --use-pnpm --import-alias "@/*" --eslint --no-turbopack --skip-install
```
Expected: scaffolds `apps/web` (keep existing `README.md` if prompted — overwrite is fine, it's the stub). If the dir-not-empty prompt blocks, move the stub: `mv apps/web/README.md /tmp/web-readme.bak` then re-run.

- [ ] **Step 2: Install deps**

```bash
cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course/apps/web
pnpm add zustand framer-motion
pnpm add -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event @types/node
pnpm install
```
Expected: deps resolve, `node_modules` present.

- [ ] **Step 3: Configure static export — `apps/web/next.config.ts`**

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",                 // static SPA for Cloudflare Pages (no server runtime)
  images: { unoptimized: true },    // required by output:'export'
  trailingSlash: true,              // stable static routing on Pages
};

export default nextConfig;
```

- [ ] **Step 4: Add Vitest config — `apps/web/vitest.config.ts`**

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
  },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
});
```

- [ ] **Step 5: Add Vitest setup — `apps/web/vitest.setup.ts`**

```typescript
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 6: Add test scripts to `apps/web/package.json`**

Add to `"scripts"`:
```json
"test": "vitest run",
"test:watch": "vitest",
"typecheck": "tsc --noEmit"
```

- [ ] **Step 7: Smoke test that the toolchain runs — `apps/web/src/lib/smoke.test.ts`**

```typescript
import { describe, it, expect } from "vitest";

describe("toolchain", () => {
  it("runs vitest", () => {
    expect(1 + 1).toBe(2);
  });
});
```

- [ ] **Step 8: Run it**

Run: `cd apps/web && pnpm test`
Expected: 1 passed.

- [ ] **Step 9: Verify the app builds (static export)**

Run: `cd apps/web && pnpm build`
Expected: build succeeds, emits `out/`.

- [ ] **Step 10: Commit**

```bash
cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course
git add apps/web
git commit -m "feat(web): scaffold Next.js static-export app + Vitest"
```

---

### Task 2: shadcn/ui init + button

**Files:**
- Create: `apps/web/components.json`, `apps/web/src/components/ui/button.tsx`, `apps/web/src/lib/utils.ts`

- [ ] **Step 1: Init shadcn (non-interactive)**

```bash
cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course/apps/web
pnpm dlx shadcn@latest init -d
pnpm dlx shadcn@latest add button drawer sheet popover dialog input badge
```
Expected: `components.json`, `src/lib/utils.ts` (with `cn()`), and `src/components/ui/*.tsx` created. `tailwind` config + globals updated by shadcn.

- [ ] **Step 2: Verify `cn` util test — `apps/web/src/lib/utils.test.ts`**

```typescript
import { describe, it, expect } from "vitest";
import { cn } from "@/lib/utils";

describe("cn", () => {
  it("merges and dedupes tailwind classes", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
    expect(cn("text-sm", false && "hidden", "font-bold")).toBe("text-sm font-bold");
  });
});
```

- [ ] **Step 3: Run**

Run: `cd apps/web && pnpm test src/lib/utils.test.ts`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course
git add apps/web
git commit -m "feat(web): shadcn/ui init + base components (button/drawer/sheet/popover/dialog/input/badge)"
```

---

### Task 3: Liquid-Glass tokens + glass primitives

**Files:**
- Modify: `apps/web/src/app/globals.css` (append tokens)
- Create: `apps/web/src/components/glass/GlassPanel.tsx`, `GlassCard.tsx`, `GlassBar.tsx`, `glass.test.tsx`

- [ ] **Step 1: Append Liquid-Glass tokens to `apps/web/src/app/globals.css`**

```css
/* ===== Liquid-Glass tokens (minimal set; planner-only) ===== */
:root {
  --glass-blur: 20px;
  --glass-bg: rgba(255, 255, 255, 0.55);
  --glass-bg-strong: rgba(255, 255, 255, 0.72);
  --glass-border: rgba(255, 255, 255, 0.6);
  --glass-radius: 16px;
  --glass-shadow: 0 8px 30px rgba(40, 50, 70, 0.14);
  --font-system: -apple-system, BlinkMacSystemFont, "SF Pro TC", "PingFang TC",
    "Microsoft JhengHei", "Segoe UI", Roboto, sans-serif;
}
.dark {
  --glass-bg: rgba(28, 30, 36, 0.55);
  --glass-bg-strong: rgba(28, 30, 36, 0.72);
  --glass-border: rgba(255, 255, 255, 0.12);
}
html { font-family: var(--font-system); }

.glass-surface {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur)) saturate(1.4);
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(1.4);
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow);
}
/* Accessibility fallbacks: opaque + no blur/motion */
@media (prefers-reduced-transparency: reduce) {
  .glass-surface { background: var(--glass-bg-strong); backdrop-filter: none; -webkit-backdrop-filter: none; }
}
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.001ms !important; transition-duration: 0.001ms !important; }
}
```

- [ ] **Step 2: Write failing test — `apps/web/src/components/glass/glass.test.tsx`**

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { GlassPanel } from "./GlassPanel";
import { GlassCard } from "./GlassCard";
import { GlassBar } from "./GlassBar";

describe("glass primitives", () => {
  it("GlassPanel renders children with glass-surface", () => {
    render(<GlassPanel data-testid="p">hi</GlassPanel>);
    const el = screen.getByTestId("p");
    expect(el).toHaveTextContent("hi");
    expect(el.className).toContain("glass-surface");
  });
  it("GlassCard and GlassBar carry glass-surface and merge className", () => {
    render(<><GlassCard data-testid="c" className="custom-c">c</GlassCard><GlassBar data-testid="b">b</GlassBar></>);
    expect(screen.getByTestId("c").className).toContain("glass-surface");
    expect(screen.getByTestId("c").className).toContain("custom-c");
    expect(screen.getByTestId("b").className).toContain("glass-surface");
  });
});
```

- [ ] **Step 3: Run to verify fail**

Run: `cd apps/web && pnpm test src/components/glass/glass.test.tsx`
Expected: FAIL (modules not found).

- [ ] **Step 4: Implement `GlassPanel.tsx`**

```tsx
import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export function GlassPanel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("glass-surface rounded-2xl", className)} {...props} />;
}
```

- [ ] **Step 5: Implement `GlassCard.tsx`**

```tsx
import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export function GlassCard({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("glass-surface rounded-xl p-3", className)} {...props} />;
}
```

- [ ] **Step 6: Implement `GlassBar.tsx`**

```tsx
import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export function GlassBar({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("glass-surface rounded-t-2xl px-4 py-2", className)} {...props} />;
}
```

- [ ] **Step 7: Run to verify pass**

Run: `cd apps/web && pnpm test src/components/glass/glass.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 8: Commit**

```bash
cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course
git add apps/web
git commit -m "feat(web): Liquid-Glass tokens + GlassPanel/GlassCard/GlassBar (reduced-transparency/motion fallbacks)"
```

---

### Task 4: Generate TS types from Pydantic contract

**Files:**
- Create: `packages/schema/generate.py`, `packages/schema/package.json`
- Generated: `packages/schema/schema.json`, `packages/schema/index.d.ts`
- Create: `apps/web/src/lib/data/types.ts` (re-export + app aliases)

- [ ] **Step 1: Write `packages/schema/generate.py`**

```python
"""Dump a combined JSON Schema (with $defs) for the v1 file roots from crawler/models.py.
Run: python packages/schema/generate.py  → writes packages/schema/schema.json
Then: pnpm --filter @ntutbox/schema generate  → index.d.ts via json-schema-to-typescript
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "crawler"))

from models import (  # noqa: E402
    TermCatalog, PeriodTable, ClassDirectory, EnrollmentLatest, Manifest,
)

ROOTS = {
    "TermCatalog": TermCatalog,
    "PeriodTable": PeriodTable,
    "ClassDirectory": ClassDirectory,
    "EnrollmentLatest": EnrollmentLatest,
    "Manifest": Manifest,
}

def main() -> None:
    combined: dict = {"title": "NtutboxCourseV1", "type": "object", "properties": {}, "$defs": {}}
    for name, model in ROOTS.items():
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        for dname, dschema in schema.pop("$defs", {}).items():
            combined["$defs"][dname] = dschema
        combined["$defs"][name] = schema
        combined["properties"][name] = {"$ref": f"#/$defs/{name}"}
    out = Path(__file__).with_name("schema.json")
    out.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write `packages/schema/package.json`**

```json
{
  "name": "@ntutbox/schema",
  "version": "0.0.0",
  "private": true,
  "scripts": {
    "schema": "python3 generate.py",
    "types": "json-schema-to-typescript --input schema.json --output index.d.ts --no-additionalProperties",
    "generate": "pnpm schema && pnpm dlx json-schema-to-typescript@15 --input schema.json --output index.d.ts"
  }
}
```

- [ ] **Step 3: Generate (run from crawler venv so Pydantic is available)**

```bash
cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course
source crawler/.venv/bin/activate
python3 packages/schema/generate.py
deactivate
cd packages/schema && pnpm dlx json-schema-to-typescript@15 --input schema.json --output index.d.ts
```
Expected: `schema.json` and `index.d.ts` written; `index.d.ts` contains `export interface TermCatalog`, `CourseOffering`, `PeriodTable`, `ClassDirectory`, `EnrollmentLatest`, `Manifest`.

- [ ] **Step 4: Verify generated names — `grep`**

Run: `grep -E "export interface (TermCatalog|CourseOffering|PeriodTable|ClassDirectory|EnrollmentLatest|Manifest)" packages/schema/index.d.ts`
Expected: all 6 present.

- [ ] **Step 5: Re-export in web — `apps/web/src/lib/data/types.ts`**

```typescript
// Single source of truth: types generated from crawler/models.py (Pydantic).
// Regenerate: cd packages/schema && pnpm generate
export type {
  TermCatalog,
  CourseOffering,
  PeriodTable,
  PeriodRef,
  ClassDirectory,
  ClassRef,
  EnrollmentLatest,
  Enrollment,
  Manifest,
  ManifestTerm,
  Meeting,
} from "../../../../../packages/schema/index";

// App-side bundle of one term's files.
export interface TermBundle {
  termKey: string;
  catalog: import("../../../../../packages/schema/index").TermCatalog;
  periods: import("../../../../../packages/schema/index").PeriodTable;
  classes: import("../../../../../packages/schema/index").ClassDirectory;
  enrollment: import("../../../../../packages/schema/index").EnrollmentLatest | null;
}
```

- [ ] **Step 6: Typecheck**

Run: `cd apps/web && pnpm typecheck`
Expected: no errors (the relative import resolves to the generated `.d.ts`).

- [ ] **Step 7: Commit**

```bash
cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course
git add packages/schema apps/web/src/lib/data/types.ts
git commit -m "feat(schema): generate TS types from Pydantic models; web consumes via packages/schema"
```

---

### Task 5: Dev fixtures (115-1 + 114-2)

**Files:**
- Create: `apps/web/public/data/v1/manifest.json`, `apps/web/public/data/v1/terms/{115-1,114-2}/{catalog,periods,classes,enrollment}.json`

- [ ] **Step 1: Copy fixtures from `data/v1`**

```bash
cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course
mkdir -p apps/web/public/data/v1/terms/115-1 apps/web/public/data/v1/terms/114-2
cp data/v1/manifest.json apps/web/public/data/v1/manifest.json
for t in 115-1 114-2; do
  cp data/v1/terms/$t/catalog.json data/v1/terms/$t/periods.json data/v1/terms/$t/classes.json data/v1/terms/$t/enrollment.json apps/web/public/data/v1/terms/$t/
done
ls -R apps/web/public/data/v1 | head -20
```
Expected: manifest + 8 term files present.

- [ ] **Step 2: Sanity-check the fixture is valid JSON and has courses**

```bash
python3 -c "import json; d=json.load(open('apps/web/public/data/v1/terms/115-1/catalog.json')); print('courses', len(d['courses']), 'term', d['term']['key'])"
```
Expected: `courses 2440 term 115-1`.

- [ ] **Step 3: Commit**

```bash
git add apps/web/public/data
git commit -m "chore(web): add dev fixtures (115-1, 114-2) for local DataSource"
```

> Note: fixtures are committed dev data (not the production source — prod fetches CDN). ~2.7MB/term is acceptable for the repo per spec §2.3.

---

### Task 6: DataSource (interface + local + cdn + env select)

**Files:**
- Create: `apps/web/src/lib/env.ts`, `lib/data/datasource.ts`, `lib/data/local-datasource.ts`, `lib/data/cdn-datasource.ts`, `lib/data/index.ts`
- Test: `lib/data/datasource.test.ts`

- [ ] **Step 1: Write `apps/web/src/lib/env.ts`**

```typescript
// Resolves the v1 data base URL. Dev default = local fixtures under /data/v1.
// Prod sets NEXT_PUBLIC_DATA_BASE_URL=https://cdn.ntutbox.com/course/v1
export function dataBaseUrl(): string {
  const v = process.env.NEXT_PUBLIC_DATA_BASE_URL?.trim();
  return v && v.length > 0 ? v.replace(/\/$/, "") : "/data/v1";
}
export function isLocalData(): boolean {
  return dataBaseUrl().startsWith("/");
}
```

- [ ] **Step 2: Write `apps/web/src/lib/data/datasource.ts`**

```typescript
import type { Manifest, TermBundle } from "./types";

export interface DataSource {
  getManifest(signal?: AbortSignal): Promise<Manifest>;
  getTerm(termKey: string, signal?: AbortSignal): Promise<TermBundle>;
}

export class DataLoadError extends Error {
  constructor(public url: string, public cause?: unknown) {
    super(`Failed to load ${url}`);
    this.name = "DataLoadError";
  }
}

// Shared fetch+parse helper (no sha256 verification in M1, per spec §2.1).
export async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, { signal });
  } catch (e) {
    throw new DataLoadError(url, e);
  }
  if (!res.ok) throw new DataLoadError(url, `HTTP ${res.status}`);
  try {
    return (await res.json()) as T;
  } catch (e) {
    throw new DataLoadError(url, e);
  }
}
```

- [ ] **Step 3: Write `apps/web/src/lib/data/cdn-datasource.ts`** (also used for local — same fetch semantics, different base)

```typescript
import type { DataSource } from "./datasource";
import { fetchJson, DataLoadError } from "./datasource";
import type { Manifest, TermBundle, TermCatalog, PeriodTable, ClassDirectory, EnrollmentLatest } from "./types";

export class HttpDataSource implements DataSource {
  constructor(private base: string) {}

  async getManifest(signal?: AbortSignal): Promise<Manifest> {
    return fetchJson<Manifest>(`${this.base}/manifest.json`, signal);
  }

  async getTerm(termKey: string, signal?: AbortSignal): Promise<TermBundle> {
    const dir = `${this.base}/terms/${termKey}`;
    const [catalog, periods, classes] = await Promise.all([
      fetchJson<TermCatalog>(`${dir}/catalog.json`, signal),
      fetchJson<PeriodTable>(`${dir}/periods.json`, signal),
      fetchJson<ClassDirectory>(`${dir}/classes.json`, signal),
    ]);
    // enrollment overlay is optional (spec §5.4): tolerate missing.
    let enrollment: EnrollmentLatest | null = null;
    try {
      enrollment = await fetchJson<EnrollmentLatest>(`${dir}/enrollment.json`, signal);
    } catch (e) {
      if (e instanceof DataLoadError && (e.cause as Error)?.name === "AbortError") throw e;
      enrollment = null;
    }
    return { termKey, catalog, periods, classes, enrollment };
  }
}
```

- [ ] **Step 4: Write `apps/web/src/lib/data/local-datasource.ts`**

```typescript
// Local fixtures share HTTP semantics (served from /public). Kept as a named export
// so the abstraction is explicit and future local-only behavior can diverge.
export { HttpDataSource as LocalDataSource } from "./cdn-datasource";
```

- [ ] **Step 5: Write `apps/web/src/lib/data/index.ts`**

```typescript
import { dataBaseUrl } from "@/lib/env";
import { HttpDataSource } from "./cdn-datasource";
import type { DataSource } from "./datasource";

let _ds: DataSource | null = null;
export function getDataSource(): DataSource {
  if (!_ds) _ds = new HttpDataSource(dataBaseUrl());
  return _ds;
}
export type { DataSource } from "./datasource";
```

- [ ] **Step 6: Write failing test — `apps/web/src/lib/data/datasource.test.ts`**

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { HttpDataSource } from "./cdn-datasource";
import { DataLoadError } from "./datasource";

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as Response;
}

describe("HttpDataSource", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("getManifest fetches <base>/manifest.json", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ schema_version: 1, terms: {} }),
    );
    const ds = new HttpDataSource("/data/v1");
    const m = await ds.getManifest();
    expect(m.schema_version).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith("/data/v1/manifest.json", { signal: undefined });
  });

  it("getTerm bundles catalog/periods/classes and tolerates missing enrollment", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      if (u.endsWith("catalog.json")) return jsonResponse({ courses: [{ offering_id: "1" }], term: { key: "115-1" } });
      if (u.endsWith("periods.json")) return jsonResponse({ periods: [] });
      if (u.endsWith("classes.json")) return jsonResponse({ classes: [] });
      return jsonResponse(null, false, 404); // enrollment missing
    });
    const ds = new HttpDataSource("/data/v1");
    const b = await ds.getTerm("115-1");
    expect(b.termKey).toBe("115-1");
    expect(b.catalog.courses).toHaveLength(1);
    expect(b.enrollment).toBeNull();
  });

  it("throws DataLoadError on non-ok manifest", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(null, false, 500));
    const ds = new HttpDataSource("/data/v1");
    await expect(ds.getManifest()).rejects.toBeInstanceOf(DataLoadError);
  });
});
```

- [ ] **Step 7: Run to verify pass**

Run: `cd apps/web && pnpm test src/lib/data/datasource.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course
git add apps/web/src/lib
git commit -m "feat(web): swappable DataSource (http/local/cdn via env) with tolerant enrollment overlay"
```

---

### Task 7: term-store (load one term, generation token, error states, timestamps)

**Files:**
- Create: `apps/web/src/store/term-store.ts`, `apps/web/src/store/term-store.test.ts`

- [ ] **Step 1: Write failing test — `apps/web/src/store/term-store.test.ts`**

```typescript
import { describe, it, expect, beforeEach, vi } from "vitest";
import { useTermStore } from "./term-store";
import type { DataSource } from "@/lib/data";
import type { TermBundle, Manifest } from "@/lib/data/types";

function fakeBundle(termKey: string): TermBundle {
  return {
    termKey,
    catalog: { schema_version: 1, term: { key: termKey, year: 115, semester: 1, label: "" },
      generated_at: null, source: {} as never, freshness: { catalog_crawled_at: "2026-06-13T05:00:00+08:00", enrollment_observed_at: null }, courses: [] },
    periods: { schema_version: 1, timezone: "Asia/Taipei", periods: [] },
    classes: { schema_version: 1, term_key: termKey, classes: [] },
    enrollment: { schema_version: 1, term_key: termKey, observed_at: "2026-06-13T05:46:00+08:00", counts: {} },
  };
}

describe("term-store", () => {
  beforeEach(() => useTermStore.setState({ status: "idle", termKey: null, bundle: null, error: null, generation: 0 }));

  it("loadTerm moves idle→loading→ready and stores bundle", async () => {
    const ds: DataSource = {
      getManifest: vi.fn(),
      getTerm: vi.fn().mockResolvedValue(fakeBundle("115-1")),
    };
    await useTermStore.getState().loadTerm("115-1", ds);
    const s = useTermStore.getState();
    expect(s.status).toBe("ready");
    expect(s.termKey).toBe("115-1");
    expect(s.catalogCrawledAt()).toBe("2026-06-13T05:00:00+08:00");
    expect(s.enrollmentObservedAt()).toBe("2026-06-13T05:46:00+08:00");
  });

  it("discards a stale (superseded) load (generation token)", async () => {
    let resolveSlow!: (b: TermBundle) => void;
    const slow = new Promise<TermBundle>((r) => (resolveSlow = r));
    const ds: DataSource = {
      getManifest: vi.fn(),
      getTerm: vi.fn()
        .mockImplementationOnce(() => slow)              // first (114-2) is slow
        .mockResolvedValueOnce(fakeBundle("115-1")),     // second (115-1) is fast
    };
    const p1 = useTermStore.getState().loadTerm("114-2", ds);
    const p2 = useTermStore.getState().loadTerm("115-1", ds);
    await p2;                                            // 115-1 finishes first
    resolveSlow(fakeBundle("114-2"));                    // stale 114-2 resolves late
    await p1;
    expect(useTermStore.getState().termKey).toBe("115-1"); // stale result ignored
  });

  it("sets status=error on failure", async () => {
    const ds: DataSource = { getManifest: vi.fn(), getTerm: vi.fn().mockRejectedValue(new Error("boom")) };
    await useTermStore.getState().loadTerm("115-1", ds);
    expect(useTermStore.getState().status).toBe("error");
    expect(useTermStore.getState().error).toContain("boom");
  });
});
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test src/store/term-store.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `apps/web/src/store/term-store.ts`**

```typescript
import { create } from "zustand";
import type { DataSource } from "@/lib/data";
import type { TermBundle } from "@/lib/data/types";

type Status = "idle" | "loading" | "ready" | "error";

interface TermState {
  status: Status;
  termKey: string | null;
  bundle: TermBundle | null;
  error: string | null;
  generation: number;
  loadTerm: (termKey: string, ds: DataSource) => Promise<void>;
  catalogCrawledAt: () => string | null;
  enrollmentObservedAt: () => string | null;
}

export const useTermStore = create<TermState>((set, get) => ({
  status: "idle",
  termKey: null,
  bundle: null,
  error: null,
  generation: 0,

  async loadTerm(termKey, ds) {
    const gen = get().generation + 1;
    set({ generation: gen, status: "loading", error: null });
    try {
      const bundle = await ds.getTerm(termKey);
      if (get().generation !== gen) return; // superseded — discard stale result
      set({ status: "ready", termKey, bundle });
    } catch (e) {
      if (get().generation !== gen) return;
      set({ status: "error", error: e instanceof Error ? e.message : String(e) });
    }
  },

  catalogCrawledAt: () => get().bundle?.catalog.freshness?.catalog_crawled_at ?? null,
  enrollmentObservedAt: () => get().bundle?.enrollment?.observed_at ?? null,
}));
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test src/store/term-store.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course
git add apps/web/src/store
git commit -m "feat(web): term-store (one-term load, generation-token stale-discard, error state, dual timestamps)"
```

---

### Task 8: Smoke page — boot, load 115-1, show counts + timestamps

**Files:**
- Modify: `apps/web/src/app/layout.tsx`, `apps/web/src/app/page.tsx`
- Test: `apps/web/src/app/page.test.tsx`

- [ ] **Step 1: Set metadata + lang in `apps/web/src/app/layout.tsx`**

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "北科盒子 排課",
  description: "北科大公開排課規劃器（免登入）",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 2: Write failing test — `apps/web/src/app/page.test.tsx`**

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// Mock the datasource module so page loads a tiny fake term.
vi.mock("@/lib/data", () => ({
  getDataSource: () => ({
    getManifest: vi.fn(),
    getTerm: vi.fn().mockResolvedValue({
      termKey: "115-1",
      catalog: { schema_version: 1, term: { key: "115-1", year: 115, semester: 1, label: "" },
        generated_at: null, source: {}, freshness: { catalog_crawled_at: "2026-06-13T05:00:00+08:00", enrollment_observed_at: null },
        courses: [{ offering_id: "1" }, { offering_id: "2" }] },
      periods: { schema_version: 1, timezone: "Asia/Taipei", periods: [] },
      classes: { schema_version: 1, term_key: "115-1", classes: [] },
      enrollment: { schema_version: 1, term_key: "115-1", observed_at: "2026-06-13T05:46:00+08:00", counts: {} },
    }),
  }),
}));

import Page from "./page";

describe("smoke page", () => {
  beforeEach(() => vi.restoreAllMocks());
  it("loads 115-1 and shows course count + catalog timestamp", async () => {
    render(<Page />);
    await waitFor(() => expect(screen.getByText(/2\s*門課/)).toBeInTheDocument());
    expect(screen.getByText(/115-1/)).toBeInTheDocument();
    expect(screen.getByText(/2026-06-13/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run to verify fail**

Run: `cd apps/web && pnpm test src/app/page.test.tsx`
Expected: FAIL.

- [ ] **Step 4: Implement `apps/web/src/app/page.tsx`**

```tsx
"use client";
import { useEffect } from "react";
import { getDataSource } from "@/lib/data";
import { useTermStore } from "@/store/term-store";
import { GlassPanel } from "@/components/glass/GlassPanel";

const DEFAULT_TERM = "115-1";

export default function Page() {
  const { status, termKey, bundle, error, loadTerm, catalogCrawledAt, enrollmentObservedAt } = useTermStore();

  useEffect(() => {
    void loadTerm(DEFAULT_TERM, getDataSource());
  }, [loadTerm]);

  return (
    <main className="min-h-dvh p-6">
      <GlassPanel className="mx-auto max-w-xl p-6">
        <h1 className="text-lg font-semibold">北科盒子 排課（M1-A 煙霧測試）</h1>
        {status === "loading" && <p className="mt-3 text-sm text-zinc-500">載入中…</p>}
        {status === "error" && (
          <p className="mt-3 text-sm text-red-600">載入失敗：{error}</p>
        )}
        {status === "ready" && bundle && (
          <div className="mt-3 space-y-1 text-sm">
            <p>學期：{termKey}（{bundle.catalog.courses.length} 門課）</p>
            <p className="text-zinc-500">目錄更新：{catalogCrawledAt() ?? "—"}</p>
            <p className="text-zinc-500">人數更新：{enrollmentObservedAt() ?? "—"}</p>
          </div>
        )}
      </GlassPanel>
    </main>
  );
}
```

- [ ] **Step 5: Run to verify pass**

Run: `cd apps/web && pnpm test src/app/page.test.tsx`
Expected: PASS.

- [ ] **Step 6: Run the full suite + typecheck + build**

Run: `cd apps/web && pnpm test && pnpm typecheck && pnpm build`
Expected: all tests pass, no type errors, static export to `out/`.

- [ ] **Step 7: Manual smoke (optional but recommended)**

Run: `cd apps/web && pnpm dev` → open `http://localhost:3000`
Expected: glass panel shows "115-1（2440 門課）" + two timestamps.

- [ ] **Step 8: Commit**

```bash
cd /Users/poterpan/Documents/Coding/NTUT/ntutbox-course
git add apps/web/src/app
git commit -m "feat(web): M1-A smoke page — boot, load 115-1, show course count + catalog/enrollment timestamps"
```

---

## Self-Review (M1-A)

**Spec coverage (§1, §2, §8):**
- §1 静态匯出 + Next/TS/Tailwind/shadcn/framer-motion → Task 1, 2. PWA/SW correctly absent (M3). ✓
- §2.1 DataSource + env switch + error states + no sha256 → Task 6. ✓
- §2.2 manifest→term load + dual timestamps → Task 7, 8. ✓ (TermSwitcher UI is M1-C; store supports switching now.)
- §2.2.1 generation-token concurrency → Task 7 (test 2). ✓
- §2.3 fixtures → Task 5. ✓
- §2.4 schema→TS gen → Task 4. ✓
- §8 glass tokens + primitives + reduced-transparency/motion → Task 3. ✓

**Out of M1-A (correctly deferred):** search/filters/conflict/credits/draft (M1-B); all UI beyond smoke page (M1-C).

**Placeholder scan:** none — every step has commands or full code.

**Type consistency:** `TermBundle` shape defined in Task 4 (`types.ts`) is consumed identically in Tasks 6/7/8. `loadTerm(termKey, ds)`, `catalogCrawledAt()`, `enrollmentObservedAt()` signatures match across store + test + page. Generated interface names verified in Task 4 Step 4.
