"use client";
import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { CourseOffering } from "@/lib/data/types";
import { CourseListItem } from "./CourseListItem";

export function CourseList({ courses }: { courses: CourseOffering[] }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const rv = useVirtualizer({
    count: courses.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 64,
    overscan: 8,
  });
  const items = rv.getVirtualItems();
  const useVirtual = items.length > 0; // jsdom has no layout → render plain list in tests

  return (
    <div ref={parentRef} className="thin-scroll h-full overflow-auto" data-testid="course-list">
      {useVirtual ? (
        <div style={{ height: rv.getTotalSize(), position: "relative" }}>
          {items.map((vi) => (
            <div
              key={courses[vi.index].offering_id}
              data-index={vi.index}
              ref={rv.measureElement}
              style={{ position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${vi.start}px)` }}
            >
              {/* pb gives the inter-card gap; measureElement includes it so rows never overlap */}
              <div className="pb-1.5">
                <CourseListItem course={courses[vi.index]} />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-1.5">
          {courses.map((c) => <CourseListItem key={c.offering_id} course={c} />)}
        </div>
      )}
    </div>
  );
}
