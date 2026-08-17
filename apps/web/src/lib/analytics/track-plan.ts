// 排課相關事件的集中 wrapper。**draft-store 不得有 GA 副作用**（§9：store 要保持
// 可測、可離線），所以 place() 只回報 outcome，要不要送事件、帶哪個 placement 由這裡決定。

import { useDraftStore } from "@/store/draft-store";
import { useTermStore } from "@/store/term-store";
import { trackEvent } from ".";
import { countBucket, type CourseAddedPlacement, type Placement } from "./events";
import { readSession, writeSession } from "./storage";

const PLAN_CREATED_PREFIX = "ntutbox_plan_created_";

/** 排入課程的唯一 UI 入口：實際 place + course_added（+ 首次排入時 plan_created）。 */
export function placeTracked(offeringId: string, placement: CourseAddedPlacement) {
  const outcome = useDraftStore.getState().place(offeringId);
  if (!outcome.added) return outcome; // 已排過（store dedup）→ 不是一次新的排課互動

  const bucket = countBucket(outcome.placedCount);
  if (bucket) {
    const termKey = currentTermKey();
    trackEvent("course_added", {
      ...(termKey ? { term_key: termKey } : {}),
      placement,
      placed_count_bucket: bucket,
    });
  }
  trackPlanCreatedTransition(outcome.previousCount, outcome.placedCount, placement);
  return outcome;
}

/**
 * 該學期 placed 由 0 → 非空時送 plan_created。只有真實 user action 會經過這裡——
 * localStorage rehydration、reconcile、換學期都不呼叫，所以不會被誤觸發。
 * 同一 session + term 用 sessionStorage guard 只送一次（§7）。
 */
export function trackPlanCreatedTransition(before: number, after: number, placement: Placement): void {
  if (before !== 0 || after <= 0) return;
  const termKey = currentTermKey();
  if (!termKey) return;
  const key = `${PLAN_CREATED_PREFIX}${termKey}`;
  if (readSession(key)) return;
  // guard 記的是「這個 session 的這個學期已經發生過 0 → 1」，與事件是否真的送出（可能未同意）
  // 無關——清空重排不該再算一次建立課表。
  writeSession(key, "1");
  trackEvent("plan_created", { term_key: termKey, placement });
}

function currentTermKey(): string | undefined {
  return useTermStore.getState().termKey ?? undefined;
}
