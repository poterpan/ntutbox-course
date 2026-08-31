import type { MetadataRoute } from "next";
import { GUIDE_PAGES, guideIndexUrl, guideUrl } from "@/lib/guide/pages";
import { loadHubCatalog } from "@/lib/hub/build-catalog";
import { buildUnitHubs } from "@/lib/hub/units";
import { SITE_ORIGIN } from "@/lib/site";

export const dynamic = "force-static"; // output: export 要求 metadata route 明確靜態

/**
 * 實體靜態路由：首頁（排課器）＋ /guide/*（說明性內容頁，清單見 lib/guide/pages.ts）
 * ＋ 課程總覽 hub 與每個開課單位一頁（lib/hub/units.ts）。
 *
 * 逐課的分享連結（2,4xx 個 `/?term=&course=`）仍在 worker 動態產的
 * sitemap-courses.xml——那份是「有哪些課程頁」，這份是「有哪些實體頁」。
 * 兩份都在 robots.ts 宣告。
 *
 * async 是因為 hub 清單要在 build 期載 catalog（loadHubCatalog）。
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const { courses } = await loadHubCatalog();
  const hubs = buildUnitHubs(courses);
  // 不出 changeFrequency / priority：Google 已明確聲明忽略這兩個欄位，留著只是雜訊。
  return [
    { url: `${SITE_ORIGIN}/` },
    { url: guideIndexUrl() },
    ...GUIDE_PAGES.map((page) => ({ url: guideUrl(page.slug) })),
    { url: `${SITE_ORIGIN}/browse/` },
    ...hubs.map((h) => ({ url: `${SITE_ORIGIN}/browse/${h.slug}/` })),
  ];
}
