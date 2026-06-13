"use client";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";
import { cn } from "@/lib/utils";

const DAY = ["日", "一", "二", "三", "四", "五", "六"];

export function CourseDetailDrawer() {
  const { byId, enrollment } = useTermCourses();
  const { detailOfferingId, openDetail } = useUiStore();
  const { favorites, placed, place, unplace, toggleFavorite } = useDraftStore();
  const c = detailOfferingId ? byId(detailOfferingId) : undefined;
  const isFav = c ? favorites.includes(c.offering_id) : false;
  const isPlaced = c ? placed.some((p) => p.offering_id === c.offering_id) : false;
  const e = c ? enrollment[c.offering_id] : undefined;

  return (
    <Dialog open={!!c} onOpenChange={(o) => { if (!o) openDetail(null); }}>
      <DialogContent className="flex h-[88vh] w-[94vw] max-w-3xl flex-col gap-0 overflow-hidden p-0">
        {c && (
          <>
            <DialogHeader className="border-b border-black/5 px-6 py-4">
              <DialogTitle className="text-xl font-bold">
                {c.name.zh}
                {c.name.en && <span className="ml-2 text-sm font-normal text-[var(--ink-soft)]">{c.name.en}</span>}
              </DialogTitle>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[var(--ink-soft)]">
                <Badge>{c.credits ?? "?"} 學分</Badge>
                {c.requirement?.symbol && <Badge>{c.requirement.symbol}</Badge>}
                {c.language && <Badge>{c.language}</Badge>}
                <span>課號 {c.offering_id}</span>
                {c.course_code && <span>· 編碼 {c.course_code}</span>}
              </div>
            </DialogHeader>

            <div className="thin-scroll flex-1 overflow-y-auto px-6 py-5">
              <dl className="grid grid-cols-1 gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
                <Row k="授課教師" v={(c.teachers ?? []).map((t) => t.name).join("、") || "—"} />
                <Row k="開課單位" v={c.unit_name ?? "—"} />
                <Row k="開課班級" v={(c.classes ?? []).map((k) => `${k.name}${k.kind === "pool" ? "(池)" : k.kind === "virtual" ? "(佔位)" : ""}`).join("、") || "—"} />
                <Row k="時數" v={c.hours != null ? String(c.hours) : "—"} />
                <Row k="上課時間" v={(c.meetings ?? []).map((m) => `週${DAY[m.day]} ${m.periods.join("、")}節`).join("；") || "—"} />
                <Row k="教室" v={(c.classrooms ?? []).map((r) => r.name).join("、") || "—"} />
                <Row k="已選人數" v={e?.enrolled_count != null ? String(e.enrolled_count) : "—"} />
                {c.tags && c.tags.length > 0 && <Row k="標籤" v={c.tags.join("、")} />}
              </dl>

              {c.notes_raw && (
                <div className="mt-5">
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--ink-soft)]">備註</h3>
                  <p className="whitespace-pre-wrap text-sm text-[var(--ink)]">{c.notes_raw}</p>
                </div>
              )}

              <div className="mt-5">
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--ink-soft)]">課程大綱</h3>
                <p className="rounded-xl bg-black/[0.03] px-3 py-3 text-sm text-[var(--ink-soft)]">
                  課綱／課程描述資料尚未匯入（來源需另爬 syllabus 頁，列於後續里程碑）。目前以課程目錄欄位為準。
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 border-t border-black/5 px-6 py-4">
              <button
                type="button"
                onClick={() => toggleFavorite(c.offering_id)}
                className={cn(
                  "flex items-center gap-1.5 rounded-xl border px-4 py-2.5 text-sm font-medium transition-colors",
                  isFav ? "border-amber-300 bg-amber-50 text-amber-600" : "border-black/10 bg-white text-[var(--ink)] hover:bg-black/5",
                )}
              >
                {isFav ? "★ 已收藏" : "☆ 收藏"}
              </button>
              {isPlaced ? (
                <button
                  type="button"
                  onClick={() => { unplace(c.offering_id); openDetail(null); }}
                  className="ml-auto rounded-xl border border-red-200 bg-red-50 px-5 py-2.5 text-sm font-semibold text-red-600 transition-colors hover:bg-red-100"
                >
                  退選（從課表移除）
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => { place(c.offering_id); openDetail(null); }}
                  className="ml-auto rounded-xl bg-[var(--accent)] px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition-[filter] hover:brightness-110"
                >
                  ＋ 排入課表
                </button>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-3">
      <dt className="w-20 shrink-0 text-[var(--ink-soft)]">{k}</dt>
      <dd className="min-w-0 flex-1 text-[var(--ink)]">{v}</dd>
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="rounded-md bg-[var(--accent)]/10 px-1.5 py-0.5 text-[11px] font-medium text-[var(--accent)]">{children}</span>;
}
