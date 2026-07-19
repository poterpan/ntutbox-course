"use client";
import type { PointerEvent } from "react";
import type { CourseOffering } from "@/lib/data/types";
import { AccentButton } from "@/components/ui/accent-button";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";
import { useIdentityStore } from "@/store/identity-store";
import { resolveMatric, libraryBadge } from "@/lib/planner/matric";
import { cn } from "@/lib/utils";

export function CourseListItem({
  course,
  mprogramOids,
}: {
  course: CourseOffering;
  // 全微學程 offering_id 聯集（見 getProgramOidSet）；未提供＝資料未達 → badge 不顯示。
  mprogramOids?: ReadonlySet<string>;
}) {
  const { favorites, placed, place, toggleFavorite } = useDraftStore();
  const openDetail = useUiStore((s) => s.openDetail);
  const setHoveredOffering = useUiStore((s) => s.setHoveredOffering);
  const userGroup = useIdentityStore((s) => s.matricGroup);
  const isFav = favorites.includes(course.offering_id);
  const isPlaced = placed.some((p) => p.offering_id === course.offering_id);
  const teachers = (course.teachers ?? []).map((t) => t.name).join("、") || "—";
  const noTime = (course.meetings ?? []).length === 0;
  // 學制徽章（學制感知）：未選學制→全標；已選→只標非本學制。
  const division = resolveMatric(course);
  const matricBadge = division ? libraryBadge(division.group, userGroup) : null;
  const inProgram = !!mprogramOids?.has(course.offering_id);

  // Desktop-only ghost preview: gate on mouse pointers so touch (tap-scroll) never
  // fires a phantom hover. (`@media (hover:hover) and (pointer:fine)` is also applied
  // on the grid side, but the JS gate is the authoritative no-touch guard.)
  const previewOn = (e: PointerEvent) => { if (e.pointerType === "mouse") setHoveredOffering(course.offering_id); };
  const previewOff = (e: PointerEvent) => { if (e.pointerType === "mouse") setHoveredOffering(null); };
  const handlePlace = () => { setHoveredOffering(null); place(course.offering_id); };

  return (
    <div
      data-offering-id={course.offering_id}
      onPointerEnter={previewOn}
      onPointerLeave={previewOff}
      className="group flex items-center gap-2 rounded-xl bg-white px-3 py-2 ring-1 ring-black/[0.07] transition-colors hover:bg-[var(--accent)]/[0.06] hover:ring-[var(--accent)]/30"
    >
      <button type="button" className="min-w-0 flex-1 text-left" onClick={() => openDetail(course.offering_id)}>
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[13px] font-semibold text-[var(--ink)]">{course.name.zh}</span>
          <span className="shrink-0 rounded-md bg-[var(--accent)]/12 px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-[var(--accent-ink)]">
            {course.credits ?? "?"} 學分
          </span>
          {matricBadge && (
            <span className={cn("shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-medium", matricBadge.className)}>
              {matricBadge.label}
            </span>
          )}
          {inProgram && (
            // 屬任一微學程（判準＝mprograms.json offering_ids 聯集）。比照學制徽章的 pastel badge 慣例，
            // 取未被學制徽章佔用的 indigo，與 accent-blue 的「學分」徽章區隔。
            <span className="shrink-0 rounded-md bg-indigo-100 px-1.5 py-0.5 text-[10px] font-medium text-indigo-700">
              微學程
            </span>
          )}
          {noTime && (
            <span className="shrink-0 rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium text-[var(--ink-soft)]">
              無時段
            </span>
          )}
        </div>
        <div className="mt-0.5 truncate text-[11px] font-medium text-[var(--ink-soft)]">
          {teachers} · {course.offering_id}
        </div>
      </button>
      <button
        type="button"
        aria-label="收藏"
        onClick={() => toggleFavorite(course.offering_id)}
        className={cn(
          "flex size-7 shrink-0 items-center justify-center rounded-lg text-base transition-colors",
          isFav ? "text-amber-500" : "text-zinc-300 hover:bg-black/5 hover:text-amber-400",
        )}
      >
        {isFav ? "★" : "☆"}
      </button>
      {isPlaced ? (
        <AccentButton
          tone="soft"
          aria-label="已排入，點擊查看或退選"
          onClick={() => openDetail(course.offering_id)}
        >
          ✓ 已排
        </AccentButton>
      ) : (
        <AccentButton aria-label="排入" onClick={handlePlace}>
          ＋ 排入
        </AccentButton>
      )}
    </div>
  );
}
