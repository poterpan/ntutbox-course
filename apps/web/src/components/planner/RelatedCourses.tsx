"use client";
import { useMemo } from "react";
import type { MouseEvent } from "react";
import type { CourseOffering } from "@/lib/data/types";
import { buildRelated, type RelatedRef } from "@/lib/hub/related";
import { courseHref } from "@/lib/share/course-link";
import { useTermCourses } from "@/lib/planner/use-term-courses";

/**
 * 課程詳情底部的交叉連結（同課其他班 / 同教師其他課 / 同單位其他課）。
 *
 * 兩個目的，缺一不可：
 * ① **爬行路徑**——每個課程頁因此有 ≤22 條指向其他課程頁的真實 `<a href>`，
 *    2,4xx 個原本互不相連的孤島變成連通圖。判準與上限見 lib/hub/related.ts。
 * ② **選課時最常問的兩件事**——「這門課還有別班嗎」「這老師還開什麼」。
 *
 * 為什麼是 `<a href>` 而不是 `<button>`：站上的「學院▾ 系所▾」等篩選器全是 button，
 * 這正是 SEO 稽核指出的核心問題——button 產生不出任何爬行路徑。這裡一定要是 anchor。
 * 使用者點擊時攔下來就地換課（不整頁重載，不清掉篩選/搜尋狀態），
 * 同時 `history.pushState` 讓網址跟著走（Next 官方支援，見 docs
 * 01-app/01-getting-started/04-linking-and-navigating.md）。修飾鍵/中鍵不攔，
 * 「在新分頁開啟」照瀏覽器原生行為走。
 */
export function RelatedCourses({
  course,
  termKey,
  onSelect,
  /** false = 就地詳情（SharedTimetableModal）：換課會動到 modal 背後的狀態、
   *  且網址代表的是分享課表，不該被改寫 → 不改網址。 */
  syncUrl = true,
}: {
  course: CourseOffering;
  termKey: string;
  onSelect: (offeringId: string) => void;
  syncUrl?: boolean;
}) {
  const { courses } = useTermCourses();
  const groups = useMemo(() => buildRelated(course, courses), [course, courses]);
  if (groups.length === 0) return null;

  return (
    <section className="mt-6 border-t border-black/5 pt-5">
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--ink-soft)]">相關課程</h3>
      <p className="mb-3 text-[11px] text-[var(--ink-faint)]">同一學期（{termKey}）內的其他開課，點擊即切換課程詳情。</p>
      <div className="space-y-4">
        {groups.map((g) => (
          <div key={g.title}>
            <h4 className="text-[11px] font-semibold text-[var(--ink)]">{g.title}</h4>
            <p className="mb-1.5 text-[10px] text-[var(--ink-faint)]">{g.hint}</p>
            <ul className="flex flex-col gap-1.5">
              {g.items.map((it) => (
                <li key={it.offeringId}>
                  <RelatedLink item={it} termKey={termKey} onSelect={onSelect} syncUrl={syncUrl} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

function RelatedLink({
  item,
  termKey,
  onSelect,
  syncUrl,
}: {
  item: RelatedRef;
  termKey: string;
  onSelect: (offeringId: string) => void;
  syncUrl: boolean;
}) {
  const href = courseHref({ termKey, offeringId: item.offeringId });

  function handleClick(e: MouseEvent<HTMLAnchorElement>) {
    // 新分頁 / 新視窗 / 已被別人處理 → 交給瀏覽器，不攔。
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    if (syncUrl && typeof window !== "undefined") window.history.pushState(null, "", href);
    onSelect(item.offeringId);
  }

  const meta = [item.classes, item.teachers, item.schedule || "無固定時段", `課號 ${item.offeringId}`]
    .filter((s) => !!s)
    .join(" · ");

  return (
    <a
      href={href}
      onClick={handleClick}
      className="flex flex-col gap-0.5 rounded-xl bg-black/[0.025] px-3 py-2 transition-colors hover:bg-[var(--accent)]/[0.08]"
    >
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="text-[13px] font-semibold text-[var(--ink)]">{item.name}</span>
        {item.credits && (
          <span className="shrink-0 rounded-md bg-[var(--accent)]/12 px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-[var(--accent-ink)]">
            {item.credits} 學分
          </span>
        )}
      </span>
      <span className="text-[11px] font-medium text-[var(--ink-soft)]">{meta}</span>
    </a>
  );
}
