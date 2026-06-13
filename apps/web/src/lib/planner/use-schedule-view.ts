"use client";
import { useMemo } from "react";
import { useDraftStore } from "@/store/draft-store";
import { useTermCourses } from "./use-term-courses";
import { conflictedSlots } from "@/lib/schedule/conflict";
import { occupantsForSlot } from "./resolve";

export function useScheduleView() {
  const placed = useDraftStore((s) => s.placed);
  const { byId } = useTermCourses();
  return useMemo(() => {
    const placedCourses = placed.map((p) => byId(p.offering_id)).filter(Boolean) as NonNullable<ReturnType<typeof byId>>[];
    const conflicted = conflictedSlots(placedCourses);
    return {
      occupants: (day: number, period: string) => occupantsForSlot(placed, byId, day, period),
      isConflicted: (day: number, period: string) => conflicted.has(`${day}-${period}`),
    };
  }, [placed, byId]);
}
