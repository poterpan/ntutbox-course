// GA4 的唯一出入口。業務元件只呼叫型別化的 trackEvent，不得自己碰 window.gtag（§5）。
//
// 閘門三道，任何一道不成立就安靜 no-op（不 throw、不 toast、不阻擋任何產品操作）：
//   1. env（NEXT_PUBLIC_GA_MEASUREMENT_ID / NEXT_PUBLIC_GA_ENABLED）+ hostname allowlist → config.ts
//   2. 使用者同意（第一方 cookie，跨 subdomain 共用）→ consent.ts
//   3. window.gtag 存在（載入失敗/被擋 → 事件留在 dataLayer，產品照跑）

import { SITE_SURFACE, analyticsAvailable, gaDebug, measurementId } from "./config";
import { readConsent } from "./consent";
import { PARAM_ALLOWLIST, type EventName, type EventParams } from "./events";
import { sanitizePage, type SanitizedPage } from "./sanitize";

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

type ConsentSignals = Record<string, "granted" | "denied">;

const DENIED_ALL: ConsentSignals = {
  analytics_storage: "denied",
  ad_storage: "denied",
  ad_user_data: "denied",
  ad_personalization: "denied",
};

// 同意後也**不開**廣告個人化（§12 明確不做 remarketing / personalization）。
const GRANTED: ConsentSignals = {
  analytics_storage: "granted",
  ad_storage: "granted",
  ad_user_data: "granted",
  ad_personalization: "denied",
};

let defaultsSet = false;
let configured = false;

/** 本地 bootstrap：建 dataLayer + 把 Consent Mode v2 四項預設成 denied。
 * 純本地佇列，**不發任何請求、不載入任何 Google 資源**（§4）。 */
export function bootstrapConsentMode(): void {
  if (typeof window === "undefined") return;
  ensureGtag();
  if (defaultsSet) return;
  defaultsSet = true;
  window.gtag?.("consent", "default", DENIED_ALL);
}

export function updateConsentMode(granted: boolean): void {
  if (typeof window === "undefined") return;
  ensureGtag();
  window.gtag?.("consent", "update", granted ? GRANTED : DENIED_ALL);
}

/** gtag('js') + config。呼叫端必須先確認同意；page_view 自己送（§6 要洗 URL）。 */
export function configureGa(): void {
  const id = measurementId();
  if (!id || configured || typeof window === "undefined") return;
  ensureGtag();
  configured = true;
  window.gtag?.("js", new Date());
  window.gtag?.("config", id, {
    send_page_view: false,
    // 兩個 subdomain 同屬 ntutbox.com，共用 GA client/session；不加跨網域 linker 裝飾網址。
    cookie_domain: "auto",
    ...(gaDebug() ? { debug_mode: true } : {}),
    ...pageFields(),
  });
}

/** 手動 page_view：同意後補送當前頁，之後只在實際 route 變更時再送。 */
export function trackPageView(): void {
  if (!canSend()) return;
  const page = sanitizePage(window.location.href, document.referrer);
  if (!page) return;
  // set 成全域參數：之後每個事件都帶洗過的 page 欄位，gtag 就不會自己去抓原始 URL。
  window.gtag?.("set", globalPageFields(page));
  trackEvent("page_view", page.term_key ? { term_key: page.term_key } : {});
}

export function trackEvent<N extends EventName>(name: N, params: EventParams[N]): void {
  if (!canSend()) return;
  try {
    window.gtag?.("event", name, { site_surface: SITE_SURFACE, ...pickAllowed(name, params) });
  } catch {
    // 分析失敗永遠不影響排課／分享／匯出（§5、§12）。
  }
}

/** 測試用：清掉 module 級的一次性 flag。 */
export function resetAnalyticsState(): void {
  defaultsSet = false;
  configured = false;
}

function canSend(): boolean {
  return analyticsAvailable() && readConsent() === "granted" && typeof window.gtag === "function";
}

function pageFields(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const page = sanitizePage(window.location.href, document.referrer);
  return page ? globalPageFields(page) : {};
}

/** term_key 是事件參數，不當全域參數（否則會黏在每一個事件上）。 */
function globalPageFields(page: SanitizedPage): Record<string, string> {
  const fields: Record<string, string> = {
    page_location: page.page_location,
    page_path: page.page_path,
  };
  if (page.page_referrer) fields.page_referrer = page.page_referrer;
  return fields;
}

/** 只放行該事件契約內的 key，且值必須是已定義的原始型別。 */
function pickAllowed(name: EventName, params: object): Record<string, string | number | boolean> {
  const allowed = PARAM_ALLOWLIST[name];
  const out: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(params)) {
    if (!allowed.includes(key)) continue;
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      out[key] = value;
    }
  }
  return out;
}

function ensureGtag(): void {
  window.dataLayer = window.dataLayer ?? [];
  if (typeof window.gtag === "function") return;
  // gtag.js 載入後會從 dataLayer 取出 arguments 物件來處理，所以必須 push `arguments`
  // 本體，不能 push 成陣列——這是 Google 官方 snippet 的形狀。
  window.gtag = function gtagShim() {
    // eslint-disable-next-line prefer-rest-params
    window.dataLayer?.push(arguments);
  };
}
