"use client";
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";
import { getDataSource } from "@/lib/data";
import type { CourseDetail } from "@/lib/data/types";
import { cn } from "@/lib/utils";

const DAY = ["日", "一", "二", "三", "四", "五", "六"];

const SYLLABUS_FIELDS: [keyof NonNullable<CourseDetail["syllabi"]>[number], string][] = [
  ["outline", "課程大綱"],
  ["schedule", "課程進度"],
  ["assessment", "評量方式"],
  ["materials", "教材／參考書"],
  ["consultation", "課程諮詢"],
  ["extended_resources", "延伸教學與資源"],
  ["sdgs", "對應 SDGs"],
  ["ai_usage", "AI 導入"],
  ["notes", "備註"],
];

export function CourseDetailDrawer() {
  const { byId, enrollment } = useTermCourses();
  const termKey = useTermStore((s) => s.termKey);
  const { detailOfferingId, openDetail } = useUiStore();
  const { favorites, placed, place, unplace, toggleFavorite } = useDraftStore();
  const c = detailOfferingId ? byId(detailOfferingId) : undefined;
  const isFav = c ? favorites.includes(c.offering_id) : false;
  const isPlaced = c ? placed.some((p) => p.offering_id === c.offering_id) : false;
  const e = c ? enrollment[c.offering_id] : undefined;

  const [detail, setDetail] = useState<CourseDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    if (!detailOfferingId || !termKey) {
      setDetail(null);
      return;
    }
    let alive = true;
    setLoadingDetail(true);
    setDetail(null);
    getDataSource()
      .getCourseDetail(termKey, detailOfferingId)
      .then((d) => { if (alive) setDetail(d); })
      .catch(() => { if (alive) setDetail(null); })
      .finally(() => { if (alive) setLoadingDetail(false); });
    return () => { alive = false; };
  }, [detailOfferingId, termKey]);

  const desc = detail?.description;
  const syllabi = detail?.syllabi ?? [];

  return (
    <Dialog open={!!c} onOpenChange={(o) => { if (!o) openDetail(null); }}>
      <DialogContent className="flex h-[88vh] w-[94vw] max-w-3xl flex-col gap-0 overflow-hidden p-0">
        {c && (
          <>
            <DialogHeader className="border-b border-black/5 px-6 py-4">
              <DialogTitle className="text-xl font-bold">
                {c.name.zh}
                {(desc?.en || c.name.en) && (
                  <span className="ml-2 text-sm font-normal text-[var(--ink-soft)]">{desc?.en || c.name.en}</span>
                )}
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
                <Section title="備註">
                  <p className="whitespace-pre-wrap text-sm text-[var(--ink)]">{c.notes_raw}</p>
                </Section>
              )}

              {/* 課程概述 (Curr description) */}
              {desc?.zh && (
                <Section title="課程概述">
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--ink)]">{desc.zh}</p>
                </Section>
              )}

              {/* 教學大綱 (per teacher) */}
              {syllabi.length > 0 && (
                <Section title="教學大綱">
                  <div className="space-y-4">
                    {syllabi.map((s, i) => (
                      <div key={i} className="rounded-xl bg-black/[0.025] p-4">
                        <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                          <span className="text-sm font-semibold text-[var(--ink)]">{s.teacher_name || "教師"}</span>
                          {s.email && (
                            <a href={`mailto:${s.email}`} className="text-xs text-[var(--accent-ink)] hover:underline">{s.email}</a>
                          )}
                          {s.updated_at && <span className="text-[10px] text-[var(--ink-faint)]">更新 {s.updated_at}</span>}
                        </div>
                        <dl className="space-y-2.5">
                          {SYLLABUS_FIELDS.map(([key, label]) => {
                            const val = s[key];
                            return typeof val === "string" && val.trim() ? (
                              <div key={key}>
                                <dt className="text-[11px] font-semibold uppercase tracking-wide text-[var(--ink-soft)]">{label}</dt>
                                <dd className="mt-0.5 whitespace-pre-wrap text-sm leading-relaxed text-[var(--ink)]">{val}</dd>
                              </div>
                            ) : null;
                          })}
                        </dl>
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {/* loading / empty states */}
              {loadingDetail && !desc && (
                <p className="mt-5 text-sm text-[var(--ink-soft)]">載入課程概述與大綱中…</p>
              )}
              {!loadingDetail && !desc?.zh && syllabi.length === 0 && (
                <p className="mt-5 rounded-xl bg-black/[0.03] px-3 py-3 text-sm text-[var(--ink-soft)]">
                  本課程暫無課程概述／教學大綱資料。
                </p>
              )}
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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-5">
      <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--ink-soft)]">{title}</h3>
      {children}
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="rounded-md bg-[var(--accent)]/10 px-1.5 py-0.5 text-[11px] font-medium text-[var(--accent-ink)]">{children}</span>;
}
