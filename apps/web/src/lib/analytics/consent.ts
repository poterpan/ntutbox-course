// 同意狀態的第一方 cookie 契約。**ntutbox.com 官網與 course.ntutbox.com 排課站共用同一份**，
// 兩邊的名稱／值／屬性必須逐字一致，否則跨 subdomain 讀不到彼此的同意（交接文檔 §4）。
//
//   name:  ntutbox_analytics_consent
//   value: granted_v1 | denied_v1
//   Domain=.ntutbox.com; Path=/; Max-Age=15552000; SameSite=Lax; Secure

export const CONSENT_COOKIE = "ntutbox_analytics_consent";
export const CONSENT_GRANTED = "granted_v1";
export const CONSENT_DENIED = "denied_v1";
export const CONSENT_MAX_AGE = 15552000; // 180 天
const SHARED_DOMAIN = ".ntutbox.com";

export type ConsentState = "granted" | "denied" | "unknown";

/** 未設過、或值是別的版本（未來 granted_v2…）→ unknown，重新詢問。 */
export function readConsent(): ConsentState {
  if (typeof document === "undefined") return "unknown";
  const raw = readCookie(CONSENT_COOKIE);
  if (raw === CONSENT_GRANTED) return "granted";
  if (raw === CONSENT_DENIED) return "denied";
  return "unknown";
}

export function writeConsent(state: "granted" | "denied"): void {
  if (typeof document === "undefined") return;
  document.cookie = consentCookieString(state, hostname(), protocol());
}

/**
 * 撤回同意：刪掉前端刪得掉的 GA/Ads cookie 與 consent cookie 本身。
 * HttpOnly 或寫在別的 domain 上的 cookie 前端刪不掉——不假裝已刪（§4）。
 */
export function clearAnalyticsCookies(): void {
  if (typeof document === "undefined") return;
  const names = new Set<string>([CONSENT_COOKIE]);
  for (const part of document.cookie.split(";")) {
    const name = part.split("=")[0]?.trim();
    if (!name) continue;
    if (name === "_ga" || name.startsWith("_ga_") || name.startsWith("_gcl_")) names.add(name);
  }
  for (const name of names) {
    for (const cookie of deletionCookieStrings(name, hostname())) document.cookie = cookie;
  }
}

/** 把 cookie 字串與當前 host 解耦，才能在測試裡驗 .ntutbox.com 上的完整屬性。 */
export function consentCookieString(state: "granted" | "denied", host: string, proto: string): string {
  const value = state === "granted" ? CONSENT_GRANTED : CONSENT_DENIED;
  const attrs = [`${CONSENT_COOKIE}=${value}`];
  const domain = sharedDomain(host);
  if (domain) attrs.push(`Domain=${domain}`);
  attrs.push("Path=/", `Max-Age=${CONSENT_MAX_AGE}`, "SameSite=Lax");
  if (proto === "https:") attrs.push("Secure");
  return attrs.join("; ");
}

/** GA 的 cookie 寫在註冊網域（cookie_domain: auto → .ntutbox.com），但 host-only 的同名
 * cookie 也可能存在（localhost / 舊資料）。兩種 Domain 都試才不會漏。 */
export function deletionCookieStrings(name: string, host: string): string[] {
  const expiry = "Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0";
  const out = [`${name}=; ${expiry}`];
  const domain = sharedDomain(host);
  if (domain) out.push(`${name}=; Domain=${domain}; ${expiry}`);
  return out;
}

/** ntutbox.com 與其 subdomain 才寫共用 Domain；localhost / preview 退化成 host-only cookie。 */
function sharedDomain(host: string): string | null {
  return host === "ntutbox.com" || host.endsWith(SHARED_DOMAIN) ? SHARED_DOMAIN : null;
}

function hostname(): string {
  return typeof window === "undefined" ? "" : window.location.hostname;
}

function protocol(): string {
  return typeof window === "undefined" ? "" : window.location.protocol;
}

function readCookie(name: string): string | null {
  for (const part of document.cookie.split(";")) {
    const eq = part.indexOf("=");
    if (eq < 0) continue;
    if (part.slice(0, eq).trim() !== name) continue;
    return decodeURIComponent(part.slice(eq + 1).trim());
  }
  return null;
}
