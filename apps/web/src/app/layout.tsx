import type { Metadata } from "next";
import "./globals.css";

const SITE_URL = "https://course.ntutbox.com";
const TITLE = "北科盒子 · 排課";
const DESCRIPTION =
  "北科盒子排課助手：查課、看課綱、排週課表，即時檢查衝堂與學分，一鍵匯入北科盒子 App。";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: TITLE, template: "%s｜北科盒子 排課" },
  description: DESCRIPTION,
  applicationName: "北科盒子 排課",
  openGraph: {
    type: "website",
    locale: "zh_TW",
    siteName: "北科盒子 排課",
    url: SITE_URL,
    title: TITLE,
    description: DESCRIPTION,
    images: [{ url: "/og.jpg", width: 1200, height: 630, alt: "北科盒子 排課" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "北科盒子 排課",
    description: DESCRIPTION,
    images: ["/og.jpg"],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
