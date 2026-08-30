import type { Metadata, Viewport } from "next";
import { dataBaseUrl, isLocalData } from "@/lib/env";
import { AnalyticsConsent } from "@/components/analytics/AnalyticsConsent";
import { GoogleAnalytics } from "@/components/analytics/GoogleAnalytics";
import "./globals.css";

const SITE_URL = "https://course.ntutbox.com";
const SITE_NAME = "北科盒子 排課";
// 首頁 title 帶搜尋字（北科大／課表規劃／課程檢索，使用者定稿）；分享連結的 title 由 edge worker 換成課名。
const TITLE = "北科盒子 排課｜北科大課表規劃・課程檢索";
const DESCRIPTION =
  "查詢國立臺北科技大學（北科大）歷年課程與課綱，排週課表、即時檢查衝堂與學分、分享課表，一鍵匯入北科盒子 App。";

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
      publisher: { "@id": `${SITE_URL}/#publisher` },
      // 課程資料的原始出處。標明非官方、資料整理自校方公開系統——E-E-A-T 稽核指出
      // 全站原本沒有任何資料來源/非官方揭露，對呈現正式課務資料的工具是信任缺口。
      isBasedOn: {
        "@type": "WebSite",
        name: "國立臺北科技大學 課程查詢系統",
        url: "https://aps.ntut.edu.tw/course/tw/",
      },
      // provider 是課程的開課單位（校方），不是本站——本站只是第三方整理者。
      // 誤標成自己會是事實錯誤，見 SEO schema 稽核。
      about: {
        "@type": "CollegeOrUniversity",
        name: "國立臺北科技大學",
        alternateName: "National Taipei University of Technology",
        url: "https://www.ntut.edu.tw/",
      },
      disambiguatingDescription:
        "本站為獨立開發的非官方工具，與國立臺北科技大學無隸屬或合作關係。課程資料整理自校方公開的課程查詢系統，每日自動更新；正式選課以學校系統為準。",
    },
    {
      "@type": "Organization",
      "@id": `${SITE_URL}/#publisher`,
      name: "北科盒子",
      url: "https://ntutbox.com",
      description: "北科盒子（NTUT Box）：北科大的非官方校務工具，含 iOS App 與網頁版排課系統。",
      sameAs: ["https://ntutbox.com", "https://github.com/poterpan/ntutbox-course"],
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
        {/* 成效分析：同意前不載入任何 Google 資源；env 未設時兩者都渲染 null。 */}
        <AnalyticsConsent />
        <GoogleAnalytics />
      </body>
    </html>
  );
}
