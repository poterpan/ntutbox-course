"use client";
import { useEffect } from "react";
import { useUiStore } from "@/store/ui-store";
import { useTermStore } from "@/store/term-store";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import { buildCourseJsonLd } from "@/lib/share/course-schema";

const NODE_ID = "course-jsonld";

/**
 * 課程詳情開著時，往 <head> 注入該課的 Course JSON-LD；關窗即移除。
 *
 * 為什麼是 client 端注入：本站是靜態 export 的單頁應用，2,461 個課程共用同一份
 * HTML，build 時無法為每個 ?course= 產生專屬結構化資料。edge worker 只改寫
 * title/description/canonical/OG（worker/index.ts），不動 JSON-LD。
 *
 * 限制（誠實記錄）：不執行 JS 的爬蟲看不到這段。要讓它們也看得到，得把課程內容
 * server-render 進 body——那是另一個層級的改動（見 SEO 稽核的 C3）。這裡先讓
 * 會渲染的 Googlebot 拿到正確的課程實體標記。
 */
export function CourseJsonLd() {
  const detailOfferingId = useUiStore((s) => s.detailOfferingId);
  const termKey = useTermStore((s) => s.termKey);
  const { byId } = useTermCourses();

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.getElementById(NODE_ID)?.remove();
    if (!detailOfferingId || !termKey) return;

    const course = byId(detailOfferingId);
    if (!course) return;
    const ld = buildCourseJsonLd({ course, termKey });
    if (!ld) return;

    const el = document.createElement("script");
    el.id = NODE_ID;
    el.type = "application/ld+json";
    el.textContent = JSON.stringify(ld);
    document.head.appendChild(el);

    return () => {
      document.getElementById(NODE_ID)?.remove();
    };
  }, [detailOfferingId, termKey, byId]);

  return null;
}
