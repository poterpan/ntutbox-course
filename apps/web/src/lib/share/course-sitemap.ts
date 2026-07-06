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

export function buildCourseSitemapXml(
  origin: string,
  termKey: string,
  names: Record<string, string>,
): string {
  const urls = Object.keys(names)
    .sort()
    .map((id) => {
      const loc = buildCourseLink({ termKey, offeringId: id, origin });
      return `<url><loc>${escapeXml(loc)}</loc></url>`;
    });
  return (
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls.join("")}</urlset>\n`
  );
}
