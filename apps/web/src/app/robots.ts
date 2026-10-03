import type { MetadataRoute } from "next";
import { AI_TRAINING_CRAWLERS } from "@/lib/seo/ai-crawlers";

export const dynamic = "force-static"; // output: export 要求 metadata route 明確靜態

// 靜態輸出成 out/robots.txt。sitemap.xml 由 Next 產（首頁 + /browse/ 課程總覽 +
// 逐系所 hub，見 app/sitemap.ts）；sitemap-courses.xml 由 edge worker 依 CDN
// 預設學期（D21）names.json 動態產（逐課分享連結，見 worker/index.ts）。
// AI 訓練爬蟲 Disallow，AI 搜尋／助理與搜尋引擎照常（D26）。實際阻擋在 Cloudflare WAF，
// 這裡是宣告，也是 Google-Extended 這類只認 robots.txt 的 token 唯一的控制方式。
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: [...AI_TRAINING_CRAWLERS], disallow: "/" },
      { userAgent: "*", allow: "/" },
    ],
    sitemap: [
      "https://course.ntutbox.com/sitemap.xml",
      "https://course.ntutbox.com/sitemap-courses.xml",
    ],
  };
}
