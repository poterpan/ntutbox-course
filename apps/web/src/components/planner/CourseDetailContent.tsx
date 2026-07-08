"use client";
import { useEffect, useState } from "react";
import { ShareIcon } from "lucide-react";
import { AccentButton } from "@/components/ui/accent-button";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";
import { getDataSource } from "@/lib/data";
import { buildCourseLink } from "@/lib/share/course-link";
import { shareOrCopy } from "@/lib/share/share-course";
import { useToast } from "@/components/ui/toast";
import type { CourseDetail } from "@/lib/data/types";
import { resolveMatric } from "@/lib/planner/matric";
import { cn } from "@/lib/utils";

const DAY = ["日", "一", "二", "三", "四", "五", "六"];

/** Dcard 北科版搜尋連結（選課常參考的評價來源）。query 走 encodeURIComponent。 */
function dcardSearchUrl(query: string) {
  return `https://www.dcard.tw/search?query=${encodeURIComponent(query)}&forum=ntut`;
}

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

/**
 * Course detail UI (info + syllabi + 收藏/排入 actions). Extracted from
 * CourseDetailDrawer so it can render BOTH inside the drawer's own Dialog and
 * in-place inside SharedTimetableModal (master↔detail, no nested dialog).
 * The Dialog wrapper + a11y title live in the caller; this renders content only.
 */
export function CourseDetailContent({
  offeringId,
  onAfterPlace,
  headerLeading,
  scrollRef,
}: {
  offeringId: string;
  onAfterPlace?: () => void;
  headerLeading?: React.ReactNode;
  scrollRef?: React.Ref<HTMLDivElement>;
}) {
  const { byId, enrollment } = useTermCourses();
  const termKey = useTermStore((s) => s.termKey);
  const { favorites, placed, place, unplace, toggleFavorite } = useDraftStore();
  const showToast = useToast((s) => s.show);
  const c = byId(offeringId);
  const isFav = c ? favorites.includes(c.offering_id) : false;
  const isPlaced = c ? placed.some((p) => p.offering_id === c.offering_id) : false;
  const e = c ? enrollment[c.offering_id] : undefined;
  const division = c ? resolveMatric(c) : null;

  const [detail, setDetail] = useState<CourseDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    if (!offeringId || !termKey) return;
    let alive = true;
    // Data-fetch effect: setting loading + clearing stale detail synchronously before the async
    // fetch is intentional (spinner + no stale flash on course switch); runs only on
    // (offeringId, termKey) change. React Compiler over-flags this.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoadingDetail(true);
    setDetail(null);
    getDataSource()
      .getCourseDetail(termKey, offeringId)
      .then((d) => { if (alive) setDetail(d); })
      .catch(() => { if (alive) setDetail(null); })
      .finally(() => { if (alive) setLoadingDetail(false); });
    return () => { alive = false; };
  }, [offeringId, termKey]);

  if (!c) return null;

  const desc = detail?.description;
  const syllabi = detail?.syllabi ?? [];
  const nameZh = c.name.zh;
  const dcardTeachers = (c.teachers ?? [])
    .map((t) => t.name)
    .filter((n): n is string => !!n?.trim());

  async function handleShare() {
    if (!c || !termKey) return;
    const url = buildCourseLink({ termKey, offeringId: c.offering_id, origin: window.location.origin });
    const name = c.name.zh ?? "課程";
    const r = await shareOrCopy(url, name, `${name}｜北科盒子 排課`);
    if (r === "copied") showToast("已複製連結");
    else if (r === "failed") showToast("複製失敗，請手動複製網址");
  }

  return (
    <>
      <div className="border-b border-black/5 px-6 py-4">
        {/* 返回鍵獨立成導覽列（僅就地詳情有 headerLeading）；與下方 badge 隔著標題、不同層級 */}
        {headerLeading && <div className="mb-1.5">{headerLeading}</div>}
        <h2 className="text-xl font-bold text-[var(--ink)]">{c.name.zh}</h2>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[var(--ink-soft)]">
          <Badge>{c.credits ?? "?"} 學分</Badge>
          {c.requirement?.symbol && <Badge>{c.requirement.symbol}</Badge>}
          {c.language && <Badge>{c.language}</Badge>}
          <span>課號 {c.offering_id}</span>
          {c.course_code && <span>· 編碼 {c.course_code}</span>}
          <button
            type="button"
            aria-label="分享此課程"
            onClick={handleShare}
            className="ml-auto flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 font-medium text-[var(--accent)] transition-colors hover:bg-[var(--accent)]/10"
          >
            <ShareIcon className="size-3.5" aria-hidden />
            分享
          </button>
        </div>
      </div>

      <div ref={scrollRef} tabIndex={-1} className="thin-scroll flex-1 overflow-y-auto overscroll-contain px-6 py-5 outline-none [touch-action:pan-y]">
        {(nameZh || dcardTeachers.length > 0) && (
          <div className="mb-5 flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--ink-soft)]">Dcard 評價</span>
            {nameZh && <DcardChip query={nameZh} label={nameZh} />}
            {dcardTeachers.map((name, i) => (
              <DcardChip key={i} query={name} label={name} />
            ))}
          </div>
        )}

        <dl className="grid grid-cols-1 gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
          <Row k="授課教師" v={(c.teachers ?? []).map((t) => t.name).join("、") || "—"} />
          <Row k="學制" v={division?.label ?? "—"} />
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

        {desc?.zh && (
          <Section title="課程概述">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--ink)]">{desc.zh}</p>
          </Section>
        )}

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
            onClick={() => { unplace(c.offering_id); onAfterPlace?.(); }}
            className="ml-auto rounded-xl border border-red-200 bg-red-50 px-5 py-2.5 text-sm font-semibold text-red-600 transition-colors hover:bg-red-100"
          >
            退選（從課表移除）
          </button>
        ) : (
          <AccentButton
            size="lg"
            className="ml-auto"
            onClick={() => { place(c.offering_id); onAfterPlace?.(); }}
          >
            ＋ 排入課表
          </AccentButton>
        )}
      </div>
    </>
  );
}

function DcardChip({ query, label }: { query: string; label: string }) {
  return (
    <a
      href={dcardSearchUrl(query)}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`在 Dcard 搜尋「${label}」`}
      className="inline-flex items-center gap-1.5 rounded-full bg-[var(--accent)]/10 py-1 pl-1.5 pr-2.5 text-xs font-medium text-[var(--accent-ink)] transition-colors hover:bg-[var(--accent)]/15"
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- static export, images.unoptimized; a tiny brand mark doesn't need next/image */}
      <img src="/dcard.png" alt="" className="size-4 shrink-0 rounded-[4px]" />
      {label}
    </a>
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
