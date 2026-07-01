"use client";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { CourseDetailContent } from "./CourseDetailContent";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useUiStore } from "@/store/ui-store";
import { useTouchScrollFocus } from "@/lib/planner/use-touch-scroll-focus";

/** Standalone course-detail overlay for the planner. The reusable detail UI
 * (info + syllabi + 收藏/排入) lives in CourseDetailContent; this is just the
 * Dialog shell + a11y title + touch-scroll focus wiring. */
export function CourseDetailDrawer() {
  const { byId } = useTermCourses();
  const { detailOfferingId, openDetail } = useUiStore();
  const c = detailOfferingId ? byId(detailOfferingId) : undefined;
  const { scrollRef, initialFocus } = useTouchScrollFocus();

  return (
    <Dialog open={!!c} onOpenChange={(o) => { if (!o) openDetail(null); }}>
      <DialogContent initialFocus={initialFocus} className="flex h-[88vh] w-[94vw] max-w-[94vw] flex-col gap-0 overflow-hidden p-0 sm:max-w-5xl">
        {c && (
          <>
            <DialogTitle className="sr-only">課程詳情</DialogTitle>
            <CourseDetailContent
              offeringId={c.offering_id}
              scrollRef={scrollRef}
              onAfterPlace={() => openDetail(null)}
            />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
