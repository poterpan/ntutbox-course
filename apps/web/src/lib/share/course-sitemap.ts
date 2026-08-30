/** Pure builders for /sitemap-courses.xml（worker 動態產：最新學期的逐課分享連結）。
 * Cloudflare-free，vitest 可測；worker/index.ts 負責抓 manifest / names.json。 */
import { buildCourseLink } from "./course-link";

/** term_key = "<民國學年>-<學期>"，逐段數值比較（"115-1" > "110-2"，且 "99-2" < "100-1"）。 */
export function latestTermKey(termKeys: string[]): string | null {
  let best: string | null = null;
  let bestVal = -1;
  for (const key of termKeys) {
    const m = /^(\d+)-(\d+)$/.exec(key);
    if (!m) continue;
    const val = Number(m[1]) * 10 + Number(m[2]);
    if (val > bestVal) {
      bestVal = val;
      best = key;
    }
  }
  return best;
}

function escapeXml(s: string): string {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

/** W3C Datetime（sitemap.org 接受的格式）。只放行能被 Date 解析、且長得像 ISO 8601 的值——
 * 寧可不出 lastmod，也不要出一個無效值讓整份 sitemap 被判格式錯誤。 */
function toLastmod(generatedAt: string | undefined): string | null {
  if (!generatedAt) return null;
  if (!/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?$/.test(generatedAt)) return null;
  return Number.isNaN(Date.parse(generatedAt)) ? null : generatedAt;
}

/**
 * @param generatedAt CDN manifest 的 `generated_at`（資料實際重新產出的時間）。
 *   給了就為每筆 URL 附 <lastmod>——課程資料在加退選期間會變動，沒有 lastmod
 *   爬蟲無從判斷新鮮度，也不利於重新排程抓取。
 */
export function buildCourseSitemapXml(
  origin: string,
  termKey: string,
  names: Record<string, string>,
  generatedAt?: string,
): string {
  const lastmod = toLastmod(generatedAt);
  const lastmodTag = lastmod ? `<lastmod>${escapeXml(lastmod)}</lastmod>` : "";
  const urls = Object.keys(names)
    .sort()
    .map((id) => {
      const loc = buildCourseLink({ termKey, offeringId: id, origin });
      return `<url><loc>${escapeXml(loc)}</loc>${lastmodTag}</url>`;
    });
  return (
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls.join("")}</urlset>\n`
  );
}
