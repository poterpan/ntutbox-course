"use client";
import { useUiStore } from "@/store/ui-store";

/** Floating pill to re-open the shared-timetable overlay after it's dismissed,
 * so the recipient can flip between their own plan and the shared one. */
export function SharedPlanFab() {
  const sharedPlan = useUiStore((s) => s.sharedPlan);
  const open = useUiStore((s) => s.sharedPlanOpen);
  const setOpen = useUiStore((s) => s.setSharedPlanOpen);
  const clear = useUiStore((s) => s.clearSharedPlan);

  if (!sharedPlan || open) return null;
  return (
    <div className="fixed bottom-44 right-4 z-40 flex items-center gap-0.5 rounded-full bg-[var(--accent)] py-1 pl-3.5 pr-1 text-sm font-semibold text-white shadow-lg sm:bottom-36 lg:bottom-20">
      <button type="button" onClick={() => setOpen(true)} className="flex items-center gap-1.5 py-1" aria-label="開啟分享的課表">
        <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden>
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M3 9h18" strokeLinecap="round" />
        </svg>
        分享的課表
      </button>
      <button
        type="button"
        aria-label="關閉分享的課表"
        onClick={clear}
        className="flex size-6 items-center justify-center rounded-full text-white/80 transition-colors hover:bg-white/20 hover:text-white"
      >
        ✕
      </button>
    </div>
  );
}
