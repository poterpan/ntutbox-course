"use client";
import { useMemo } from "react";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useUiStore } from "@/store/ui-store";
import { applyFilters } from "@/lib/filters/apply";
import { search } from "@/lib/search/search";
import { buildIndex } from "@/lib/search/build-index";
import { CourseSearchBar } from "./CourseSearchBar";
import { FilterChips } from "./FilterChips";
import { CourseList } from "./CourseList";

export function CourseLibrary() {
  const { courses, classes } = useTermCourses();
  const { query, filters } = useUiStore();

  const units = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of courses) if (c.unit_code) m.set(c.unit_code, c.unit_name ?? c.unit_code);
    return [...m].map(([code, name]) => ({ code, name }));
  }, [courses]);

  const results = useMemo(() => {
    const filtered = applyFilters(courses, filters);
    const ids = new Set(search(buildIndex(filtered), query).map((d) => d.offeringId));
    return filtered.filter((c) => ids.has(c.offering_id));
  }, [courses, filters, query]);

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <CourseSearchBar />
      <FilterChips units={units} classes={classes.map((k) => ({ code: k.code, name: k.name ?? k.code, kind: k.kind }))} />
      <div className="text-[11px] text-zinc-500">{results.length} 門課{results.length >= 200 ? "（已達上限，請縮小條件）" : ""}</div>
      <div className="min-h-0 flex-1"><CourseList courses={results.slice(0, 200)} /></div>
    </div>
  );
}
