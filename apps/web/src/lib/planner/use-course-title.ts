"use client";
import { useEffect, useRef } from "react";
import { useUiStore } from "@/store/ui-store";
import { useTermCourses } from "./use-term-courses";

/** 首頁固定 title，與 app/layout.tsx 的 metadata.title.default 一致。 */
export const HOME_TITLE = "北科盒子 排課｜北科大課表規劃・課程檢索";

/** 課程 title 格式，與 lib/share/og.ts 的 resolveShareOg 一致。 */
export function courseTitle(name: string): string {
  return `${name}｜北科盒子 排課`;
}

/**
 * document.title 的唯一擁有者：跟著「目前開著哪一堂課的詳情」走。
 *
 * 為什麼需要這支：edge worker 會用 HTMLRewriter 把分享連結的 <title> 改成課名
 * （worker/index.ts），但 hydration 時 Next 會用 layout.tsx 的 metadata.title.default
 * 蓋回去。Googlebot 讀的是渲染後的 DOM，不補這一步，sitemap 裡 2,461 個課程 URL
 * 在索引端 title 全部相同。
 *
 * 由 detailOfferingId 驅動（而非只在分享連結進站時寫一次），確保關窗、切課、
 * 切學期都會回到首頁 title，不會停在上一堂課的名字。
 *
 * ⚠️ 卸載時**只在 title 仍是本 hook 寫的那個值**才還原成首頁 title。原本無條件還原，
 * 在只有 "/" 一個路由時看不出問題；`/browse/**` hub 頁上線後，從首頁 client-side
 * 導航過去會變成：Next 先套上 hub 頁的 metadata title → planner 卸載 → 這裡把它蓋回
 * 首頁 title（實測 /browse/ 的 tab 標題變成首頁標題）。document.title 是全域、本 hook
 * 不獨佔它，所以還原前要先確認沒有別人已經接手。
 *
 * **只寫不讀** document.title——analytics/config.ts 的鐵則是絕不可讀它當 GA 的
 * page_title（課名進 GA 違反個資規範）；這裡單向寫入不影響該邊界。
 */
export function useCourseTitle() {
  const detailOfferingId = useUiStore((s) => s.detailOfferingId);
  const { byId } = useTermCourses();

  // 本 hook 最後寫進 document.title 的值（卸載時的所有權判準）。
  const writtenRef = useRef<string | null>(null);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const name = detailOfferingId ? byId(detailOfferingId)?.name?.zh : null;
    const next = name ? courseTitle(name) : HOME_TITLE;
    document.title = next;
    writtenRef.current = next;
    return () => {
      // 已被別人（如 hub 頁的 metadata）改掉 → 那是新頁面的 title，別搶回來。
      if (document.title !== writtenRef.current) return;
      document.title = HOME_TITLE;
      writtenRef.current = HOME_TITLE;
    };
  }, [detailOfferingId, byId]);
}
