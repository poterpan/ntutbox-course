import type { Metadata } from "next";
import "./globals.css";

const SITE_URL = "https://course.ntutbox.com";
const TITLE = "北科盒子 排課 — 台北科大公開排課規劃";
const DESCRIPTION =
  "台北科大公開、免登入的排課規劃器：查課、排週課表，即時檢查衝堂／學分／選課階段。排好一鍵匯入北科盒子 App 送件。";

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
  },
  twitter: {
    card: "summary_large_image",
    title: "北科盒子 排課",
    description: "台北科大公開、免登入的排課規劃器。",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
