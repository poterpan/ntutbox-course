"use client";
import { useMemo } from "react";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useSearchIndex } from "@/lib/planner/use-search-index";
import { useMprograms } from "@/lib/planner/use-mprograms";
import { getProgramOidSet } from "@/lib/planner/mprogram-index";
import { useTermStore } from "@/store/term-store";
import { useUiStore } from "@/store/ui-store";
import { applyFilters } from "@/lib/filters/apply";
import { collegeOf } from "@/lib/filters/college-map";
import { search } from "@/lib/search/search";
import { SearchInput } from "@/components/ui/search-input";
import { FilterBar } from "./FilterBar";
import { CourseList } from "./CourseList";

const CAP = 200;

export function CourseLibrary() {
  const { courses, classes } = useTermCourses();
  const index = useSearchIndex();
  const { query, setQuery, filters } = useUiStore();

  // 微學程目錄容器層取一次（module-cache，避免 per-row fetch），供 badge + 三態篩選共用同一份聯集集合。
  const storeTermKey = useTermStore((s) => s.termKey);
  const selectedTerm = useUiStore((s) => s.selectedTerm);
  const { data: mprogDir } = useMprograms(storeTermKey ?? selectedTerm);
  const mprogramOids = getProgramOidSet(mprogDir); // WeakMap memo：同 dir 參照回同一 set

  // 系所 options — narrowed to the selected 學院 (學院→系所 cascade)
  const units = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of courses) if (c.unit_code) m.set(c.unit_code, c.unit_name ?? c.unit_code);
    let list = [...m].map(([code, name]) => ({ code, name }));
    if (filters.colleges.length) list = list.filter((u) => filters.colleges.includes(collegeOf(u.code)));
    return list.sort((a, b) => a.name.localeCompare(b.name));
  }, [courses, filters.colleges]);

  // 班級 options — narrowed to selected 系所 (or 學院 if no 系所) — 學院→系所→班級 cascade
  const classOpts = useMemo(() => {
    let list = classes;
    if (filters.units.length) list = list.filter((k) => k.unit_code != null && filters.units.includes(k.unit_code));
    else if (filters.colleges.length) list = list.filter((k) => filters.colleges.includes(collegeOf(k.unit_code)));
    return list.map((k) => ({ code: k.code, name: k.name ?? k.code, kind: k.kind }));
  }, [classes, filters.units, filters.colleges]);

  const results = useMemo(() => {
    const filtered = applyFilters(courses, filters, mprogramOids);
    if (!query.trim()) return filtered;
    const searchIds = new Set(search(index, query).map((d) => d.offeringId));
    return filtered.filter((c) => searchIds.has(c.offering_id));
  }, [courses, index, filters, query, mprogramOids]);

  return (
    <div className="flex h-full flex-col gap-3 p-4 pt-3">
      {/* prominent search */}
      <SearchInput
        variant="prominent"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="搜尋課程、教師或課號…"
        aria-label="搜尋課程"
      />

      <FilterBar units={units} classes={classOpts} mprogramReady={!!mprogDir} />

      <div className="text-[11px] tabular-nums text-[var(--ink-soft)]">
        {results.length} 門{results.length > CAP ? `（顯示前 ${CAP}）` : ""}
      </div>

      <div className="min-h-0 flex-1">
        {results.length === 0 ? (
          <p className="pt-8 text-center text-sm text-[var(--ink-soft)]">沒有符合的課程，試著放寬條件</p>
        ) : (
          <CourseList courses={results.slice(0, CAP)} mprogramOids={mprogramOids} />
        )}
      </div>
    </div>
  );
}
