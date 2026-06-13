import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "北科盒子 排課",
  description: "北科大公開排課規劃器（免登入）",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
