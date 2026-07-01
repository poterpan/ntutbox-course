"use client";
import { useMemo } from "react";
import { useDraftStore } from "@/store/draft-store";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { creditSummary } from "@/lib/schedule/credits";
import { GlassBar } from "@/components/glass/GlassBar";
import { useTermStore } from "@/store/term-store";
import { buildPlanLink } from "@/lib/share/plan-link";
import { shareOrCopy } from "@/lib/share/share-course";
import { useToast } from "@/components/ui/toast";
import { AccentButton } from "@/components/ui/accent-button";

export function CreditSummary() {
  const placed = useDraftStore((s) => s.placed);
  const { byId } = useTermCourses();
  const s = useMemo(() => creditSummary(placed, byId), [placed, byId]);
  const termKey = useTermStore((st) => st.termKey);
  const showToast = useToast((st) => st.show);

  async function handleSharePlan() {
    if (!termKey || placed.length === 0) return;
    const offeringIds = [...placed].sort((a, b) => a.priority - b.priority).map((p) => p.offering_id);
    const url = buildPlanLink({ termKey, offeringIds, origin: window.location.origin });
    const r = await shareOrCopy(url, "我的課表", "我的課表｜北科盒子 排課");
    if (r === "copied") showToast("已複製課表連結");
    else if (r === "failed") showToast("複製失敗，請手動複製網址");
  }

  return (
    <GlassBar className="mx-3 mb-3 flex flex-col gap-2.5 rounded-2xl px-5 py-2.5 sm:mx-4 sm:flex-row sm:items-center sm:gap-4">
      {/* 數據帶：一行可掃視、各項同級（不再有超大字） */}
      <div className="flex flex-1 flex-wrap items-center gap-x-2.5 gap-y-1 text-xs tabular-nums text-[var(--ink-soft)]">
        <span>
          排入 <b className="font-semibold text-[var(--ink)]">{placed.length}</b> 門 ·{" "}
          <b className="font-semibold text-[var(--ink)]">{s.placedCredits}</b> 學分
        </span>
        <span aria-hidden className="text-[var(--ink-faint)]">·</span>
        <span className={s.conflictGroupCount > 0 ? "font-semibold text-orange-600" : undefined}>
          衝堂 <b className={s.conflictGroupCount > 0 ? "text-orange-600" : "text-[var(--ink)]"}>{s.conflictGroupCount}</b>
        </span>
        <span aria-hidden className="text-[var(--ink-faint)]">·</span>
        <span>
          第一志願 <b className="font-semibold text-[var(--accent-ink)]">{s.firstChoiceCredits}</b> 學分
        </span>
        {s.unknownCreditCount > 0 && (
          <>
            <span aria-hidden className="text-[var(--ink-faint)]">·</span>
            <span className="text-[var(--ink-faint)]">學分未知 {s.unknownCreditCount}</span>
          </>
        )}
      </div>

      {/* 動作：手機全寬、桌機靠右。未來「匯出到 App」= primary，分享退為 icon。 */}
      <div className="flex items-center gap-2">
        <AccentButton
          tone="soft"
          size="lg"
          onClick={handleSharePlan}
          disabled={placed.length === 0}
          aria-label="分享課表"
          className="w-full sm:w-auto"
        >
          <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden>
            <path d="M12 3v12" strokeLinecap="round" />
            <path d="M8 7l4-4 4 4" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" strokeLinecap="round" />
          </svg>
          分享課表
        </AccentButton>
      </div>
    </GlassBar>
  );
}
