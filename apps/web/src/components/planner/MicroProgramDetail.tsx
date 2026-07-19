"use client";
import { useMemo } from "react";
import { ChevronLeftIcon } from "lucide-react";
import { useUiStore } from "@/store/ui-store";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { cn } from "@/lib/utils";
import { filterChipVariants } from "@/components/ui/filter-chip";
import { OAA_MPROGRAM_URL } from "@/lib/planner/mprogram-links";
import type { CourseOffering, MicroProgram, MicroProgramCourse } from "@/lib/data/types";

// 課程標準分類固定順序；category=null 歸「其他」置末（見 Task 13 brief §3）。
const CATEGORY_ORDER = ["基礎", "核心", "總整", "進階", "應用"] as const;
const OTHER = "其他";

// 班級 chip 文字：本學期該 offering 的班級名（多班以「、」併），無班級碼退回課號。
function classLabel(o: CourseOffering): string {
  const names = (o.classes ?? []).map((k) => k.name ?? k.code).filter(Boolean);
  return names.join("、") || o.offering_id;
}

function ChipButton({ oid, label, onOpen }: { oid: string; label: string; onOpen: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(oid)}
      // 可點提示：比照微學程列表列的 accent hover（列表用 ring，chip 用 border）。
      // 覆寫 filterChipVariants inactive 的 hover:bg-white（twMerge 收斂）。
      className={cn(
        filterChipVariants({ active: false }),
        "hover:border-[var(--accent)]/30 hover:bg-[var(--accent)]/10",
      )}
    >
      {label}
    </button>
  );
}

function OaaLink() {
  return (
    <a
      href={OAA_MPROGRAM_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="text-[12px] text-[var(--ink-soft)] underline"
    >
      教務處微學程專區（完整規定與 PDF）↗
    </a>
  );
}

export function MicroProgramDetail({ program }: { program: MicroProgram }) {
  const openDetail = useUiStore((s) => s.openDetail);
  const setSelectedProgramCode = useUiStore((s) => s.setSelectedProgramCode);
  const { byId } = useTermCourses();

  // 本學期開課依 course_code 分桶；反查不到的 oid（不在 catalog，理論不發生）另存純文字列出（spec §4 防呆）。
  const { offeringsByCode, orphanOids } = useMemo(() => {
    const byCode = new Map<string, CourseOffering[]>();
    const orphans: string[] = [];
    for (const oid of program.offering_ids ?? []) {
      const o = byId(oid);
      if (!o || !o.course_code) {
        orphans.push(oid);
        continue;
      }
      const list = byCode.get(o.course_code);
      if (list) list.push(o);
      else byCode.set(o.course_code, [o]);
    }
    return { offeringsByCode: byCode, orphanOids: orphans };
  }, [program.offering_ids, byId]);

  const groups = useMemo(() => {
    const buckets = new Map<string, MicroProgramCourse[]>();
    // course_code（課程編碼）在課程標準清單可重複出現（同編碼多列）→ 去重，避免重複列與 React key 衝突。
    const seen = new Set<string>();
    for (const c of program.courses ?? []) {
      if (seen.has(c.course_code)) continue;
      seen.add(c.course_code);
      const key = c.category ?? OTHER;
      const list = buckets.get(key);
      if (list) list.push(c);
      else buckets.set(key, [c]);
    }
    return [...CATEGORY_ORDER, OTHER]
      .map((title) => ({ title, courses: buckets.get(title) ?? [] }))
      .filter((g) => g.courses.length > 0);
  }, [program.courses]);

  const hasStandard = (program.courses ?? []).length > 0;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-black/[0.06] px-3 py-2.5">
        <button
          type="button"
          aria-label="返回微學程列表"
          onClick={() => setSelectedProgramCode(null)}
          className="-ml-1 flex shrink-0 items-center rounded-lg p-1.5 text-[var(--accent)] transition-colors hover:bg-[var(--accent)]/10"
        >
          <ChevronLeftIcon className="size-5" aria-hidden />
        </button>
        <h2 className="min-w-0 flex-1 truncate text-[15px] font-semibold text-[var(--ink)]">{program.name}</h2>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        <p className="text-[12px] text-[var(--ink-soft)]">
          112 學年度起入學之日間部大學部，畢業前須完成跨領域學習（微學程為五種路徑之一）；修讀須於教務處公告期間登記。
        </p>

        {hasStandard ? (
          <div className="mt-4 flex flex-col gap-4">
            {groups.map((g) => (
              <section key={g.title}>
                <h3 className="text-[13px] font-semibold text-[var(--ink)]">{g.title}</h3>
                <ul className="mt-1.5 flex flex-col gap-2">
                  {g.courses.map((c) => {
                    const offerings = offeringsByCode.get(c.course_code) ?? [];
                    return (
                      <li key={c.course_code} className="rounded-xl bg-white px-3 py-2.5 ring-1 ring-black/[0.07]">
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="text-[13px] text-[var(--ink)]">{c.name_zh}</span>
                          {c.credits != null && (
                            <span className="shrink-0 text-[11px] tabular-nums text-[var(--ink-soft)]">{c.credits} 學分</span>
                          )}
                        </div>
                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                          {offerings.map((o) => (
                            <ChipButton key={o.offering_id} oid={o.offering_id} label={classLabel(o)} onOpen={openDetail} />
                          ))}
                          {c.online ? (
                            // notes 含 e＝ewant 線上課程（不走選課系統，catalog 查無開班）；如實標示，取代誤導的「本學期未開」。
                            <span className="rounded-md px-1.5 py-0.5 text-[11px] text-[var(--ink-soft)] ring-1 ring-black/[0.07]">
                              線上課程
                            </span>
                          ) : (
                            offerings.length === 0 && (
                              <span className="text-[11px] text-[var(--ink-soft)]">本學期未開</span>
                            )
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
            {orphanOids.length > 0 && (
              <p className="text-[11px] text-[var(--ink-faint)]">其他開課：{orphanOids.join("、")}</p>
            )}
          </div>
        ) : (
          <div className="mt-4 flex flex-col gap-2">
            <p className="text-[12px] text-[var(--ink-soft)]">課程標準暫缺，僅列本學期開課</p>
            <div className="flex flex-wrap items-center gap-1.5">
              {(program.offering_ids ?? []).map((oid) => {
                const o = byId(oid);
                return <ChipButton key={oid} oid={oid} label={o ? classLabel(o) : oid} onOpen={openDetail} />;
              })}
            </div>
          </div>
        )}

        <div className="mt-5 border-t border-black/[0.06] pt-3">
          {program.rules_text ? (
            <details>
              <summary className="cursor-pointer text-[13px] font-medium text-[var(--ink)]">修讀規則（原文）</summary>
              <p className="mt-2 whitespace-pre-line text-[13px] leading-relaxed text-[var(--ink-soft)]">
                {program.rules_text}
              </p>
            </details>
          ) : (
            <p className="text-[12px] text-[var(--ink-soft)]">規定原文暫缺，請以教務處專區為準</p>
          )}
          <div className="mt-3">
            <OaaLink />
          </div>
        </div>
      </div>
    </div>
  );
}
