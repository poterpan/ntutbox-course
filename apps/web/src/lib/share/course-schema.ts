/** 課程頁的 schema.org Course JSON-LD。Pure function，vitest 可測；
 * 由 CourseJsonLd 元件在詳情開啟時注入 <head>。 */
import type { CourseOffering } from "@/lib/data/types";

const SITE_ORIGIN = "https://course.ntutbox.com";

/** 開課單位是校方，不是本站——本站只是第三方整理者。
 * 把 provider 標成自己會是事實錯誤（見 SEO schema 稽核的風險評估）。 */
const NTUT = {
  "@type": "CollegeOrUniversity",
  name: "國立臺北科技大學",
  alternateName: "National Taipei University of Technology",
  url: "https://www.ntut.edu.tw/",
} as const;

export interface CourseJsonLdInput {
  course: CourseOffering;
  termKey: string;
}

/**
 * 產生 Course + CourseInstance。只輸出**資料真的有**的欄位——寧可少標，
 * 也不要為了湊 rich result 需求而杜撰（缺欄位就整個省略該屬性）。
 *
 * 註：Google 的 Course rich result 目前僅支援英文內容，本站全繁中拿不到該 SERP
 * 特性；標這段的目的是語意完整性與 AI/其他消費端的可讀性，不是為了 Google 星等。
 */
export function buildCourseJsonLd({ course, termKey }: CourseJsonLdInput): Record<string, unknown> | null {
  const name = course.name?.zh;
  if (!name) return null;

  const url = `${SITE_ORIGIN}/?term=${encodeURIComponent(termKey)}&course=${encodeURIComponent(course.offering_id)}`;
  const instructors = (course.teachers ?? [])
    .map((t) => t?.name)
    .filter((n): n is string => !!n)
    .map((n) => ({ "@type": "Person", name: n }));

  const instance: Record<string, unknown> = {
    "@type": "CourseInstance",
    // 線下授課：資料有教室就是實體課；沒有教室資訊時不臆測 courseMode。
    ...(course.classrooms?.length ? { courseMode: "onsite" } : {}),
    ...(instructors.length ? { instructor: instructors } : {}),
    ...(course.classrooms?.length
      ? {
          location: course.classrooms
            .map((r) => r?.name)
            .filter((n): n is string => !!n)
            .map((n) => ({ "@type": "Place", name: n })),
        }
      : {}),
  };

  const credits = course.credits != null ? Number(course.credits) : null;

  return {
    "@context": "https://schema.org",
    "@type": "Course",
    "@id": `${url}#course`,
    url,
    name,
    ...(course.name?.en ? { alternateName: course.name.en } : {}),
    // course_code 跨學期固定，是這門課的穩定識別碼（offering_id 每學期跳動）。
    ...(course.course_code ? { courseCode: course.course_code } : {}),
    inLanguage: "zh-Hant",
    isAccessibleForFree: false,
    provider: NTUT,
    ...(course.unit_name
      ? { department: { "@type": "Organization", name: course.unit_name } }
      : {}),
    ...(credits != null && Number.isFinite(credits) && credits > 0
      ? { numberOfCredits: credits }
      : {}),
    hasCourseInstance: instance,
  };
}
