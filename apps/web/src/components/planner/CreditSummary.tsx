"use client";
import { useMemo, useState } from "react";
import { ExternalLinkIcon, ShareIcon } from "lucide-react";
import { useDraftStore } from "@/store/draft-store";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { creditSummary } from "@/lib/schedule/credits";
import { GlassBar } from "@/components/glass/GlassBar";
import { useTermStore } from "@/store/term-store";
import { buildPlanLink } from "@/lib/share/plan-link";
import { shareOrCopy } from "@/lib/share/share-course";
import { useToast } from "@/components/ui/toast";
import { AccentButton } from "@/components/ui/accent-button";
import { trackEvent } from "@/lib/analytics";
import { countBucket } from "@/lib/analytics/events";
import { submitOrder } from "@/lib/planner/submit-order";
import { ExportToAppDialog } from "./ExportToAppDialog";

export function CreditSummary() {
  const placed = useDraftStore((s) => s.placed);
  const { byId } = useTermCourses();
  const s = useMemo(() => creditSummary(placed, byId), [placed, byId]);
  const termKey = useTermStore((st) => st.termKey);
  const showToast = useToast((st) => st.show);

  const [exportOpen, setExportOpen] = useState(false);

  async function handleSharePlan() {
    if (!termKey || placed.length === 0) return;
    // 全站統一：分享連結與匯出 payload 都吃 submitOrder，讓「網頁看到的順序」＝
    // 「App 看到的順序」＝「未來送出的順序」。
    const offeringIds = submitOrder(placed, byId).map((o) => o.offeringId);
    const url = buildPlanLink({ termKey, offeringIds, origin: window.location.origin });
    const r = await shareOrCopy(url, "我的課表", "我的課表｜北科盒子 排課");
    if (r === "copied") showToast("已複製課表連結");
    else if (r === "failed") showToast("複製失敗，請手動複製網址");
    // 成功分享/複製才算一次擴散；使用者取消（shareOrCopy 回 "shared"）也算，failed 不送。
    const bucket = countBucket(placed.length);
    if (r !== "failed" && bucket) {
      trackEvent("plan_shared", {
        term_key: termKey,
        share_method: r === "shared" ? "web_share" : "copy",
        course_count_bucket: bucket,
      });
    }
  }

  return (
    <>
      <GlassBar className="mx-3 mb-3 flex flex-col gap-1.5 rounded-2xl px-4 py-2.5 sm:mx-4 sm:flex-row sm:items-center sm:gap-4 sm:px-5">
        {/* 數據列（一行、含顯眼的第一志願學分大數字當錨點）— 固定不與動作同行，避免窄機翻行 */}
        <div className="flex flex-1 flex-wrap items-baseline gap-x-2.5 gap-y-1 text-xs tabular-nums text-[var(--ink-soft)]">
          <span className="flex items-baseline gap-1.5">
            <span className="font-medium">第一志願學分</span>
            <b className="text-xl font-bold text-[var(--accent-ink)]">{s.firstChoiceCredits}</b>
          </span>
          <span aria-hidden className="text-[var(--ink-faint)]">·</span>
          <span>排入 <b className="font-semibold text-[var(--ink)]">{placed.length}</b> 門 · <b className="font-semibold text-[var(--ink)]">{s.placedCredits}</b> 學分</span>
          <span aria-hidden className="text-[var(--ink-faint)]">·</span>
          <span className={s.conflictGroupCount > 0 ? "font-semibold text-orange-600" : undefined}>衝堂 {s.conflictGroupCount}</span>
          {s.unknownCreditCount > 0 && (
            <>
              <span aria-hidden className="text-[var(--ink-faint)]">·</span>
              <span className="text-[var(--ink-faint)]">學分未知 {s.unknownCreditCount}</span>
            </>
          )}
        </div>

        {/* 動作列：匯出到 App（primary）+ 分享課表（soft）兩顆平分整列，
            主次靠顏色而非尺寸——不做成全頁最大的按鈕。手機各半、桌機靠右 auto。 */}
        <div className="flex items-center gap-2">
          <AccentButton
            tone="solid"
            size="lg"
            onClick={() => setExportOpen(true)}
            disabled={placed.length === 0}
            className="flex-1 gap-1.5 sm:flex-none"
          >
            <ExternalLinkIcon className="size-4" aria-hidden />
            匯出到 App
          </AccentButton>
          <AccentButton
            tone="soft"
            size="lg"
            onClick={handleSharePlan}
            disabled={placed.length === 0}
            className="flex-1 gap-1.5 sm:flex-none"
          >
            <ShareIcon className="size-4" aria-hidden />
            分享課表
          </AccentButton>
        </div>
      </GlassBar>
      <ExportToAppDialog open={exportOpen} onOpenChange={setExportOpen} />
    </>
  );
}
