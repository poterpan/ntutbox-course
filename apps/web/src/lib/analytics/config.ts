// GA4 開關與宿主閘門。Measurement ID / 開關是 **build-time** `NEXT_PUBLIC_*`（同 lib/env.ts 慣例）——
// wrangler.jsonc 的 `vars` 進不了 client bundle，必須設在 Cloudflare Workers Builds 的
// build environment variables。全部缺席 → 整站完全 no-op。

// production property 只允許在這三個 host 收資料（§2）；localhost / *.workers.dev preview
// 不送，避免污染正式報表。需要 DebugView 時另設一組 debug stream + NEXT_PUBLIC_GA_DEBUG=true。
const ALLOWED_HOSTS = new Set(["course.ntutbox.com", "ntutbox.com", "www.ntutbox.com"]);

export const SITE_SURFACE = "course" as const;

/**
 * 送給 GA 的固定 page_title（＝collect payload 的 `dt`）。
 *
 * ⚠️ 不要改成讀 `document.title`。edge worker 會把分享連結的 `<title>` 改寫成
 * 「⟨課名⟩｜北科盒子 排課」或「分享的課表 · N 門課｜北科盒子 排課」（worker/index.ts
 * + lib/share/og.ts），而 GA4 **預設自動收集 page_title**——不覆寫就會讓這個維度
 * 隨課名浮動。
 *
 * 理由是**報表維度衛生**，不是個資：`page_title` 是 GA4 的報表維度，若讓 2,461 個
 * 課名各成一個維度值，報表會碎掉、也無法再用它做站級彙總（如「排課頁總瀏覽數」）。
 * 分享課表的「N 門課」同理，精確值當維度沒有分析價值。
 *
 * 想量測課程層級的行為（例如未來的熱門課程）→ 送**結構化 custom event**
 * （如 `course_view` 帶 `offering_id` 參數），維度乾淨、可查詢、可匯出。
 * 不要靠 page_title 這個維度硬塞。
 *
 * 註：這與 repo 根 CLAUDE.md「不得 commit 個資」無關——那條管的是進版控的檔案內容，
 * 不涵蓋執行期匿名統計。查課/排課行為本來就是正常的分析對象。
 */
export const PAGE_TITLE = "北科盒子 排課";

export function measurementId(): string | null {
  const v = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID?.trim();
  return v && v.length > 0 ? v : null;
}

export function gaEnabled(): boolean {
  return process.env.NEXT_PUBLIC_GA_ENABLED?.trim() === "true";
}

/** debug stream 逃生門：讓另一組測試用 Measurement ID 能在 localhost / preview 跑，
 * 而不必把 production property 的 host 閘門放寬。 */
export function gaDebug(): boolean {
  return process.env.NEXT_PUBLIC_GA_DEBUG?.trim() === "true";
}

export function isAllowedHost(hostname?: string): boolean {
  if (gaDebug()) return true;
  const h = hostname ?? (typeof window === "undefined" ? "" : window.location.hostname);
  return ALLOWED_HOSTS.has(h);
}

/** GA 在這個環境「可不可以跑」——env 齊備 + 開關開 + host 允許。
 * 同意狀態是另一道獨立閘門（見 consent.ts），未同意時一律不載入任何 Google 資源。 */
export function analyticsAvailable(): boolean {
  if (typeof window === "undefined") return false;
  return measurementId() !== null && gaEnabled() && isAllowedHost();
}
