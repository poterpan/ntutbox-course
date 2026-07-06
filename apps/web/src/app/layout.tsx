import type { Metadata, Viewport } from "next";
import { dataBaseUrl, isLocalData } from "@/lib/env";
import "./globals.css";

const SITE_URL = "https://course.ntutbox.com";
const SITE_NAME = "北科盒子 排課";
// 首頁 title 帶搜尋字（北科大／課表規劃／課程檢索，使用者定稿）；分享連結的 title 由 edge worker 換成課名。
const TITLE = "北科盒子 排課｜北科大課表規劃・課程檢索";
const DESCRIPTION =
  "免登入查詢國立臺北科技大學（北科大）歷年課程與課綱，排週課表、即時檢查衝堂與學分、分享課表，一鍵匯入北科盒子 App。";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: TITLE, template: `%s｜${SITE_NAME}` },
  description: DESCRIPTION,
  applicationName: SITE_NAME,
  keywords: ["北科", "北科大", "臺北科技大學", "台北科技大學", "NTUT", "選課", "排課", "課表", "課程查詢", "北科盒子"],
  // 分享連結（/?course=、/?plan=）與首頁同一頁：預設全部 canonical 到 "/"，
  // 課程分享連結由 worker 改寫成 self-canonical（見 worker/index.ts）。
  alternates: { canonical: "/" },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1 },
  },
  appleWebApp: { capable: true, title: "北科排課", statusBarStyle: "default" },
  formatDetection: { telephone: false }, // 課號是純數字，避免 iOS 誤判成電話
  openGraph: {
    type: "website",
    locale: "zh_TW",
    siteName: SITE_NAME,
    url: SITE_URL,
    title: TITLE,
    description: DESCRIPTION,
    images: [{ url: "/og.jpg", width: 1200, height: 630, alt: SITE_NAME }],
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_NAME,
    description: DESCRIPTION,
    images: ["/og.jpg"],
  },
};

export const viewport: Viewport = {
  // globals.css body 漸層的頂端底色（light）／.dark 底色
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#eef2fb" },
    { media: "(prefers-color-scheme: dark)", color: "#0f131c" },
  ],
};

// Google「網站名稱」吃 WebSite、應用資訊吃 WebApplication；同站以 @graph 併一份。
const JSON_LD = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      url: `${SITE_URL}/`,
      name: SITE_NAME,
      alternateName: "北科排課",
      inLanguage: "zh-Hant",
    },
    {
      "@type": "WebApplication",
      "@id": `${SITE_URL}/#app`,
      url: `${SITE_URL}/`,
      name: SITE_NAME,
      description: DESCRIPTION,
      applicationCategory: "EducationalApplication",
      operatingSystem: "Any",
      browserRequirements: "Requires JavaScript",
      inLanguage: "zh-Hant",
      isAccessibleForFree: true,
      offers: { "@type": "Offer", price: "0", priceCurrency: "TWD" },
      publisher: { "@type": "Organization", name: "北科盒子" },
    },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // 課程資料在另一個 origin（cdn.ntutbox.com）；先 preconnect 省掉首次抓資料的握手。
  const dataOrigin = isLocalData() ? null : new URL(dataBaseUrl()).origin;
  return (
    <html lang="zh-Hant">
      <body>
        {dataOrigin && <link rel="preconnect" href={dataOrigin} crossOrigin="anonymous" />}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
        {children}
      </body>
    </html>
  );
}
