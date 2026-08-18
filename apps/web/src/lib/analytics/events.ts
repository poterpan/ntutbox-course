// 事件契約（交接文檔 §7）。所有名稱 lower_snake_case、所有參數值都是固定 enum 或 bucket——
// **絕不放使用者輸入**（搜尋原文、課號、課名、教師名、plan payload 一律禁止）。
// 數量只送 bucket，避免用精確序列重建某個人的課表。

import type { FilterState } from "@/lib/filters/types";

/** 真實排入入口。micro_program 不存在於本站（微學程面板只開詳情頁 → 歸入 detail）。 */
export type Placement = "course_list" | "detail" | "slot" | "shared_import";
/** 分享課表匯入是「一次動作 N 門課」，不送 course_added（會灌水），故不含 shared_import。 */
export type CourseAddedPlacement = Exclude<Placement, "shared_import">;
/** placeholder = F-C 匯出流程還沒上線時的佔位鈕；真 handoff 上線後用前兩者區隔。 */
export type HandoffMethod = "universal_link" | "qr" | "placeholder";
export type ShareMethod = "web_share" | "copy";
export type CampaignKey = "google_ads_1151";
export type CountBucket = "1" | "2_5" | "6_plus";
export type ResultBucket = "0" | "1_10" | "11_50" | "51_plus";
export type FilterCountBucket = "0" | "1" | "2_plus";
/** allowlisted error code；不可送 exception/message/payload。 */
export type ExportErrorCode = "empty_plan" | "invalid_plan" | "payload_build_failed" | "handoff_unavailable";

export interface EventParams {
  page_view: { term_key?: string };
  course_search: {
    term_key?: string;
    result_bucket: ResultBucket;
    filter_count_bucket: FilterCountBucket;
  };
  course_added: {
    term_key?: string;
    placement: CourseAddedPlacement;
    placed_count_bucket: CountBucket;
  };
  plan_created: { term_key?: string; placement: Placement };
  plan_shared: {
    term_key?: string;
    share_method: ShareMethod;
    course_count_bucket: CountBucket;
  };
  /** 主要 Web conversion。「click」不代表 App 已開啟，報表不得宣稱成功匯入。 */
  export_to_app_click: {
    term_key?: string;
    handoff_method: HandoffMethod;
    course_count_bucket: CountBucket;
    campaign_key?: CampaignKey;
  };
  // ↓ 以下兩個本次**未接線**：F-C 匯出流程（payload 產生／驗證／未安裝 fallback）還不存在，
  //   沒有正確的掛載點。型別先定義好，接點上線再埋。
  export_to_app_error: { term_key?: string; error_code: ExportErrorCode };
  app_store_click: {
    placement: "export_fallback";
    campaign_token: "course_google_1151";
    campaign_key?: CampaignKey;
  };
}

export type EventName = keyof EventParams;

/** Runtime 第二道防線：型別擋不住 `as never` 或未來重構，送出前只放行這些 key。
 * site_surface 由 trackEvent 自己加，不在這裡。 */
export const PARAM_ALLOWLIST: Record<EventName, readonly string[]> = {
  page_view: ["term_key"],
  course_search: ["term_key", "result_bucket", "filter_count_bucket"],
  course_added: ["term_key", "placement", "placed_count_bucket"],
  plan_created: ["term_key", "placement"],
  plan_shared: ["term_key", "share_method", "course_count_bucket"],
  export_to_app_click: ["term_key", "handoff_method", "course_count_bucket", "campaign_key"],
  export_to_app_error: ["term_key", "error_code"],
  app_store_click: ["placement", "campaign_token", "campaign_key"],
};

/** 0 門 → null（沒有「0」bucket；呼叫端遇到 null 就不送事件）。 */
export function countBucket(n: number): CountBucket | null {
  if (n <= 0) return null;
  if (n === 1) return "1";
  return n <= 5 ? "2_5" : "6_plus";
}

export function resultBucket(n: number): ResultBucket {
  if (n <= 0) return "0";
  if (n <= 10) return "1_10";
  return n <= 50 ? "11_50" : "51_plus";
}

export function filterCountBucket(n: number): FilterCountBucket {
  return n <= 0 ? "0" : n === 1 ? "1" : "2_plus";
}

/** 啟用中的篩選「維度」數（不是選了幾個值）——維度數才反映使用者縮小範圍的程度。 */
export function activeFilterCount(f: FilterState): number {
  let n = 0;
  if (f.weekdays.length) n++;
  if (f.periods.length) n++;
  if (f.colleges.length) n++;
  if (f.units.length) n++;
  if (f.classes.length) n++;
  if (f.categories.length) n++;
  if (f.emi !== "all") n++;
  if (f.mprogram !== "all") n++;
  return n;
}
