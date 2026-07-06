import type { MetadataRoute } from "next";

export const dynamic = "force-static"; // output: export 要求 metadata route 明確靜態

// PWA manifest（靜態輸出成 out/manifest.webmanifest；Next 會自動在 head 加 link）。
// 顏色對齊 globals.css body 漸層底色；icon 走 app-dir metadata route（/icon.png）。
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "北科盒子 排課",
    short_name: "北科排課",
    description:
      "免登入查詢國立臺北科技大學（北科大）歷年課程與課綱，排週課表、即時檢查衝堂與學分、分享課表，一鍵匯入北科盒子 App。",
    id: "/",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    lang: "zh-Hant",
    background_color: "#eef2fb",
    theme_color: "#eef2fb",
    icons: [
      { src: "/icon.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/apple-icon.png", sizes: "180x180", type: "image/png" },
    ],
  };
}
