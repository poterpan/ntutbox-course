// URL / referrer 清洗（交接文檔 §6）。GA4 預設會把完整 query 當 page_location 送出，
// 而排課站的 ?plan= / ?course= / 未來匯入 payload 絕不能離站，所以 page_location、
// page_path、page_referrer 一律先過這裡。
//
// 這支不依賴 use-share-link 的清 URL 時序（effect 誰先跑不保證）——sanitizer 自己防守。

const UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"] as const;
const CLICK_ID_KEYS = ["gclid", "gbraid", "wbraid"] as const;
const CLICK_ID_CHARS = /^[A-Za-z0-9._~-]+$/;
const UTM_MAX_LEN = 128;
const CLICK_ID_MAX_LEN = 512;

/** 合法學期字串（115-1 等）。只有符合的 ?term 才轉成事件參數，且不留在 page_location。 */
export const TERM_KEY_RE = /^\d{3}-[12]$/;

export interface SanitizedPage {
  page_location: string;
  page_path: string;
  page_referrer?: string;
  /** 由 ?term 轉出的事件參數；呼叫端自行決定要不要附在事件上。 */
  term_key?: string;
}

export function sanitizePage(href: string, referrer?: string): SanitizedPage | null {
  const url = safeUrl(href);
  if (!url) return null;

  // allowlist-only 重建 query：plan / course / payload / token / code 與任何未知參數都不會被抄過來。
  // 用 encodeURIComponent 而非 URLSearchParams：後者是 form-encoding，會把 click ID 裡合法的
  // `~` 轉成 %7E、空白轉成 `+`，歸因比對時最好保持位元級一致。
  const kept: string[] = [];
  for (const key of UTM_KEYS) {
    const v = cleanUtm(url.searchParams.get(key));
    if (v) kept.push(`${key}=${encodeURIComponent(v)}`);
  }
  for (const key of CLICK_ID_KEYS) {
    const v = cleanClickId(url.searchParams.get(key));
    if (v) kept.push(`${key}=${encodeURIComponent(v)}`);
  }

  const query = kept.join("&");
  const path = url.pathname + (query ? `?${query}` : "");
  const page: SanitizedPage = {
    // hash 一律丟掉（重建自 origin + pathname + 白名單 query）。
    page_location: url.origin + path,
    page_path: path,
  };

  const referrerValue = referrer ? sanitizeReferrer(referrer) : undefined;
  if (referrerValue) page.page_referrer = referrerValue;

  const term = url.searchParams.get("term");
  if (term && TERM_KEY_RE.test(term)) page.term_key = term;

  return page;
}

/** referrer 只保留 origin + pathname（query/hash 可能帶別站的敏感參數）。 */
export function sanitizeReferrer(referrer: string): string | undefined {
  const url = safeUrl(referrer);
  return url ? url.origin + url.pathname : undefined;
}

function safeUrl(value: string): URL | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url : null;
  } catch {
    return null;
  }
}

/** utm_*：去控制字元後仍超長 → 整個丟棄，不截斷後勉強使用（§6）。 */
function cleanUtm(raw: string | null): string | null {
  if (!raw) return null;
  const v = stripControlChars(raw);
  if (v.length === 0 || v.length > UTM_MAX_LEN) return null;
  return v;
}

function cleanClickId(raw: string | null): string | null {
  if (!raw) return null;
  if (raw.length > CLICK_ID_MAX_LEN || !CLICK_ID_CHARS.test(raw)) return null;
  return raw;
}

/** C0（含 NUL/換行）與 C1 控制字元。寫成 code-point 判斷而非正則字面值，
 * 免得原始碼裡出現肉眼看不見的控制字元。 */
function stripControlChars(value: string): string {
  let out = "";
  for (const ch of value) {
    const code = ch.codePointAt(0) ?? 0;
    if (code <= 0x1f || (code >= 0x7f && code <= 0x9f)) continue;
    out += ch;
  }
  return out;
}
