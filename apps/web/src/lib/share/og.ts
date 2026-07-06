/** Pure share-link OG resolution. Kept Cloudflare-free so it unit-tests in vitest;
 * worker/index.ts wires the network (names.json fetch) + HTMLRewriter around it. */
import { buildCourseLink } from "./course-link";

export function planCount(plan: string): number {
  return plan.split(".").filter(Boolean).length;
}

export interface ShareOg {
  title: string;
  description: string;
  /** 這個分享連結該 canonical 到的 path+query；null＝維持預設（"/"）。
   * 課程連結是有限、可索引的集合 → self-canonical（並進 sitemap-courses.xml）；
   * plan 連結是無限排列組合 → 一律 canonical 回首頁。 */
  canonicalPath: string | null;
}

export function resolveShareOg(
  params: URLSearchParams,
  names: Record<string, string> | null,
): ShareOg | null {
  const course = params.get("course");
  if (course) {
    const name = names?.[course];
    if (!name) return null;
    const term = params.get("term");
    return {
      title: `${name}｜北科盒子 排課`,
      description: `查看北科「${name}」課程資訊，加入你的課表、檢查衝堂與學分`,
      canonicalPath: term ? buildCourseLink({ termKey: term, offeringId: course, origin: "" }) : null,
    };
  }
  const plan = params.get("plan");
  if (plan) {
    const n = planCount(plan);
    if (n < 1) return null;
    return {
      title: `分享的課表 · ${n} 門課｜北科盒子 排課`,
      description: `查看這份 ${n} 門課的課表規劃`,
      canonicalPath: null,
    };
  }
  return null;
}
