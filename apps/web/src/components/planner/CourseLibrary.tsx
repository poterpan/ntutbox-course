"use client";
import { useMemo } from "react";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useSearchIndex } from "@/lib/planner/use-search-index";
import { useUiStore } from "@/store/ui-store";
import { applyFilters } from "@/lib/filters/apply";
import { search } from "@/lib/search/search";
import { CourseSearchBar } from "./CourseSearchBar";
import { FilterChips } from "./FilterChips";
import { CourseList } from "./CourseList";

export function CourseLibrary() {
  const { courses, classes } = useTermCourses();
  const index = useSearchIndex();
  const { query, filters } = useUiStore();

  const units = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of courses) if (c.unit_code) m.set(c.unit_code, c.unit_name ?? c.unit_code);
    return [...m].map(([code, name]) => ({ code, name }));
  }, [courses]);

  const results = useMemo(() => {
    const filteredIds = new Set(applyFilters(courses, filters).map((c) => c.offering_id));
    const searchIds = new Set(search(index, query).map((d) => d.offeringId));
    return courses.filter((c) => filteredIds.has(c.offering_id) && searchIds.has(c.offering_id));
  }, [courses, index, filters, query]);

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <CourseSearchBar />
      <FilterChips units={units} classes={classes.map((k) => ({ code: k.code, name: k.name ?? k.code, kind: k.kind }))} />
      <div className="text-[11px] text-zinc-500">{results.length} 門課{results.length >= 200 ? "（已達上限，請縮小條件）" : ""}</div>
      <div className="min-h-0 flex-1"><CourseList courses={results.slice(0, 200)} /></div>
    </div>
  );
}
