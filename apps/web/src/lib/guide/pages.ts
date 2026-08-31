/**
 * 指南頁（/guide/*）的路由註冊表 —— hub 卡片、sitemap、breadcrumb、JSON-LD 共用同一份。
 *
 * 為什麼要註冊表：新增一頁時只改這裡，sitemap 與 hub 不會漏。
 * （sitemap.ts 是手寫清單，歷史上很容易忘記同步。）
 *
 * 站台 origin 依既有慣例逐模組寫死（見 lib/share/course-schema.ts:5、app/sitemap.ts），
 * 不從 metadataBase 取——這些字串也要給 sitemap / JSON-LD 用，那裡拿不到 metadata context。
 */
import type { Metadata } from "next";

export const SITE_ORIGIN = "https://course.ntutbox.com";

/** next.config.ts trailingSlash: true —— 站內所有指南連結一律帶結尾斜線。 */
export const GUIDE_PATH = "/guide/";

export type GuideSlug =
  | "timetable"
  | "selection-phases"
  | "general-education"
  | "micro-programs";

export interface GuidePageMeta {
  slug: GuideSlug;
  /** <title>；會套 layout 的 `%s｜北科盒子 排課` 模板，所以不重複站名。 */
  title: string;
  /** 頁面 h1；比 title 更完整可讀。 */
  heading: string;
  /** meta description ＋ JSON-LD description。 */
  description: string;
  /** hub 卡片上的一句「這頁回答什麼」。 */
  answers: string;
}

export const GUIDE_INDEX = {
  title: "北科大選課與查課指南",
  heading: "北科大選課與查課指南",
  description:
    "整理北科大（臺北科技大學）查課與選課的實務知識：節次與上課時間對照、課號與修別符號怎麼看、四種選課機制的差別、通識博雅與微學程怎麼修。非官方整理，一律以學校公告為準。",
} as const;

export const GUIDE_PAGES: readonly GuidePageMeta[] = [
  {
    slug: "timetable",
    title: "北科大課表怎麼看：節次時間、課號、修別符號",
    heading: "北科大課表怎麼看：節次、課號與修別符號",
    description:
      "北科大的節次不是 1 到 14，而是 1234N56789ABCD。這頁整理節次與上課時間對照表、課號與課程編碼的差別、修別符號（△▲☆★）的意思，以及課程查詢系統查不到的欄位。",
    answers: "節次 N 和 A–D 是幾點？課號和課程編碼差在哪？△▲☆★ 是什麼意思？",
  },
  {
    slug: "selection-phases",
    title: "北科大選課注意事項：四種選課機制的差別",
    heading: "北科大選課注意事項：四種機制，別當成同一件事",
    description:
      "北科大的「選課」其實分成期末網路初選、志願選填分發、開學後加退選、獨立登記四種機制，能選的課不一樣。這頁整理各階段的範圍、常見錯誤訊息的意思，以及排課時該先確認什麼。",
    answers: "哪些課初選就能選？哪些要等加退選？「※不是本班課程※」是什麼意思？",
  },
  {
    slug: "general-education",
    title: "北科大通識課程怎麼選：博雅四向度、體育、共同英文",
    heading: "北科大通識課程怎麼選：博雅、體育與共同英文",
    description:
      "北科大通識包含博雅課程、體育與共同英文，選課方式和專業課不同——多半是志願選填分發而非先搶先贏。這頁整理博雅的四個向度、課程池班級與佔位課為什麼看起來很怪。",
    answers: "博雅有哪幾個向度？為什麼班級寫「博雅課程(三)」？體育怎麼選？",
  },
  {
    slug: "micro-programs",
    title: "北科大微學程怎麼修：登記修讀與課程分類",
    heading: "北科大微學程怎麼修：登記修讀是另一件事",
    description:
      "北科大微學程的課照常在選課系統加選，但「加入微學程」是另一套教務處登記程序，不是選課動作。這頁整理兩者的差別、微學程課程的基礎／核心／總整分類，以及線上課程的例外。",
    answers: "微學程要在哪裡登記？課要另外選嗎？基礎／核心／總整是什麼？",
  },
];

export function guidePath(slug: GuideSlug): string {
  return `${GUIDE_PATH}${slug}/`;
}

export function guideUrl(slug: GuideSlug): string {
  return `${SITE_ORIGIN}${guidePath(slug)}`;
}

export function guideIndexUrl(): string {
  return `${SITE_ORIGIN}${GUIDE_PATH}`;
}

/** 除了 `slug` 這頁以外的其他指南頁——給頁尾「其他指南」用。 */
export function otherGuidePages(slug: GuideSlug): GuidePageMeta[] {
  return GUIDE_PAGES.filter((p) => p.slug !== slug);
}

export function guidePageBySlug(slug: GuideSlug): GuidePageMeta {
  const page = GUIDE_PAGES.find((p) => p.slug === slug);
  if (!page) throw new Error(`unknown guide slug: ${slug}`);
  return page;
}

/**
 * 子頁的 metadata。
 *
 * ⚠️ `alternates.canonical` 一定要給：root layout 把 canonical 釘在 "/"（因為課程／課表
 * 分享連結全是首頁的 query string），子路由若不覆蓋，整個 /guide/* 會 canonical 到首頁
 * 而不被索引。這個函式存在的主要理由就是避免逐頁漏寫。
 */
export function guideMetadata(page: GuidePageMeta): Metadata {
  const path = guidePath(page.slug);
  return {
    title: page.title,
    description: page.description,
    alternates: { canonical: path },
    openGraph: {
      type: "article",
      url: path,
      title: page.title,
      description: page.description,
    },
  };
}
