// course_search 節流（§7）：停止操作 500ms 後才送，且對「正規化後的匿名狀態」去重
// （同一組 bucket 不重送）。**搜尋原文永遠不進 signature、也不進事件參數。**

import { trackEvent } from ".";
import { filterCountBucket, resultBucket } from "./events";

const DEBOUNCE_MS = 500;

export interface SearchSnapshot {
  termKey: string | null;
  /** 只帶「有沒有 query」，不帶內容。 */
  hasQuery: boolean;
  filterCount: number;
  resultCount: number;
}

let timer: ReturnType<typeof setTimeout> | null = null;
let lastSentSignature: string | null = null;

export function reportSearchState(snapshot: SearchSnapshot): void {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  // 既沒 query 也沒 filter → 不是一次「找課」，不送；並清掉去重狀態，
  // 讓使用者清空後重打同一組條件仍算新的一次搜尋。
  if (!snapshot.hasQuery && snapshot.filterCount <= 0) {
    lastSentSignature = null;
    return;
  }

  const params = {
    ...(snapshot.termKey ? { term_key: snapshot.termKey } : {}),
    result_bucket: resultBucket(snapshot.resultCount),
    filter_count_bucket: filterCountBucket(snapshot.filterCount),
  };
  const signature = [
    snapshot.termKey ?? "",
    snapshot.hasQuery ? "q" : "-",
    params.result_bucket,
    params.filter_count_bucket,
  ].join("|");

  timer = setTimeout(() => {
    timer = null;
    if (signature === lastSentSignature) return;
    lastSentSignature = signature;
    trackEvent("course_search", params);
  }, DEBOUNCE_MS);
}

/** 測試用：清掉 pending timer 與去重狀態。 */
export function resetSearchTracker(): void {
  if (timer) clearTimeout(timer);
  timer = null;
  lastSentSignature = null;
}
