"use client";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";

export function CourseDetailDrawer() {
  const { byId } = useTermCourses();
  const { detailOfferingId, openDetail } = useUiStore();
  const { favorites, placed, place, toggleFavorite } = useDraftStore();
  const c = detailOfferingId ? byId(detailOfferingId) : undefined;

  // Sheet uses @base-ui/react Dialog under the hood.
  // onOpenChange: (open: boolean, eventDetails) => void — we only need the first arg.
  return (
    <Sheet open={!!c} onOpenChange={(o) => { if (!o) openDetail(null); }}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        {c && (
          <>
            <SheetHeader>
              <SheetTitle>
                <span>{c.name.zh}</span>
                {c.name.en && <span className="ml-1 text-sm font-normal text-zinc-500">（{c.name.en}）</span>}
              </SheetTitle>
            </SheetHeader>
            <dl className="mt-4 space-y-2 text-sm">
              <Row k="課號" v={c.offering_id} />
              <Row k="課程編碼" v={c.course_code ?? "—"} />
              <Row k="學分" v={String(c.credits ?? "未知")} />
              <Row k="教師" v={(c.teachers ?? []).map((t) => t.name).join("、") || "—"} />
              <Row k="開課單位" v={c.unit_name ?? "—"} />
              <Row k="開課班級" v={(c.classes ?? []).map((k) => k.name).join("、") || "—"} />
              <Row k="授課語言" v={c.language ?? "—"} />
              <Row k="節次" v={(c.meetings ?? []).map((m) => `星期${m.day} ${m.periods.join(",")}`).join("；") || "—"} />
              <Row k="備註" v={c.notes_raw || "—"} />
            </dl>
            <div className="mt-4 flex gap-2">
              <Button variant="outline" className="flex-1" onClick={() => toggleFavorite(c.offering_id)}>
                {favorites.includes(c.offering_id) ? "★ 已收藏" : "☆ 收藏"}
              </Button>
              <Button
                className="flex-1"
                disabled={placed.some((p) => p.offering_id === c.offering_id)}
                onClick={() => place(c.offering_id)}
              >
                ＋ 排入
              </Button>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-20 shrink-0 text-zinc-400">{k}</dt>
      <dd className="flex-1 text-zinc-800">{v}</dd>
    </div>
  );
}
