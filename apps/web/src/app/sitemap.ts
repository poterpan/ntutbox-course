import type { MetadataRoute } from "next";
import { GUIDE_PAGES, guideIndexUrl, guideUrl } from "@/lib/guide/pages";

export const dynamic = "force-static"; // output: export 要求 metadata route 明確靜態

// 實體路由＝首頁（排課器）＋ /guide/*（說明性內容頁，清單見 lib/guide/pages.ts）。
// 逐課的分享連結在 worker 動態產的 sitemap-courses.xml。
export default function sitemap(): MetadataRoute.Sitemap {
  // 不出 changeFrequency / priority：Google 已明確聲明忽略這兩個欄位，留著只是雜訊。
  return [
    { url: "https://course.ntutbox.com/" },
    { url: guideIndexUrl() },
    ...GUIDE_PAGES.map((page) => ({ url: guideUrl(page.slug) })),
  ];
}
