import type { MetadataRoute } from "next";

export const dynamic = "force-static"; // output: export 要求 metadata route 明確靜態

// 只有一個實體路由（"/"）；逐課的分享連結在 worker 動態產的 sitemap-courses.xml。
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: "https://course.ntutbox.com/",
      changeFrequency: "weekly",
      priority: 1,
    },
  ];
}
