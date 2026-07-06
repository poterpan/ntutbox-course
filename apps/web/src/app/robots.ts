import type { MetadataRoute } from "next";

export const dynamic = "force-static"; // output: export 要求 metadata route 明確靜態

// 靜態輸出成 out/robots.txt。sitemap.xml 由 Next 產（首頁）；
// sitemap-courses.xml 由 edge worker 依 CDN 最新學期 names.json 動態產（見 worker/index.ts）。
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: [
      "https://course.ntutbox.com/sitemap.xml",
      "https://course.ntutbox.com/sitemap-courses.xml",
    ],
  };
}
