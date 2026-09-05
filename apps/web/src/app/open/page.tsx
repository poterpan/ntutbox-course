import type { Metadata } from "next";

import { PlanOpen } from "./PlanOpen";

export const metadata: Metadata = {
  title: "在 App 中開啟預排課表",
  // 不索引：這一頁只有帶 fragment 才有意義，而 fragment 不會被爬蟲看到，
  // 收錄進搜尋結果只會讓人點進一個空頁面。
  robots: { index: false },
};

export default function OpenPage() {
  return <PlanOpen />;
}
