"use client";
import { useMemo } from "react";
import { useTermStore } from "@/store/term-store";
import type { CourseOffering } from "@/lib/data/types";

export function useTermCourses() {
  const bundle = useTermStore((s) => s.bundle);
  return useMemo(() => {
    const courses: CourseOffering[] = bundle?.catalog.courses ?? [];
    const map = new Map(courses.map((c) => [c.offering_id, c]));
    return {
      courses,
      byId: (id: string) => map.get(id),
      periods: bundle?.periods,
      classes: bundle?.classes?.classes ?? [],
      enrollment: bundle?.enrollment?.counts ?? {},
      validIds: new Set(courses.map((c) => c.offering_id)),
    };
  }, [bundle]);
}
