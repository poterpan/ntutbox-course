/**
 * 指南頁的 JSON-LD builder。Pure function，vitest 可測；由 server component 直接
 * `JSON.stringify` 進 <script type="application/ld+json">（同 app/layout.tsx 的作法）。
 *
 * 為什麼只標這兩種：
 * - **BreadcrumbList**：目前仍是 Google 實際支援的 rich result，站內層級 /guide/ → 子頁
 *   本來就存在，標了不是為了效益而杜撰結構。
 * - **Article**：語意完整性（給 AI / 其他消費端），不是為了 Google 星等——比照
 *   lib/share/course-schema.ts 的註記。
 *
 * 刻意**不**標：
 * - `FAQPage`：Google 已於 2026-05 移除該 SERP 特性，為效益新增只是無效標記。
 * - `QAPage`：那是給「使用者提問、多人作答」的社群 Q&A 頁用的；本站頁面是編輯整理的
 *   說明文字，沒有真實提問者與答覆，標了是事實錯誤。
 * - `HowTo`：同樣已被 Google 移除。
 * - `dateModified`：沒有可信的逐頁最後修改時間可用；寧可省略也不要放一個會腐爛的
 *   常數（同 lib/share/course-sitemap.ts 刻意不出 <lastmod> 的理由）。
 */
import {
  GUIDE_INDEX,
  SITE_ORIGIN,
  guideIndexUrl,
  guideUrl,
  type GuidePageMeta,
} from "./pages";

/** 開課與制度的權威是校方，不是本站；`about` 指向學校，別把自己標成來源。 */
const NTUT = {
  "@type": "CollegeOrUniversity",
  name: "國立臺北科技大學",
  alternateName: "National Taipei University of Technology",
  url: "https://www.ntut.edu.tw/",
} as const;

export interface BreadcrumbItem {
  name: string;
  url: string;
}

export function buildBreadcrumbJsonLd(items: readonly BreadcrumbItem[]): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: item.name,
      item: item.url,
    })),
  };
}

/** 首頁 → 選課指南（hub 自己就停在這裡）。 */
export function guideIndexBreadcrumb(): BreadcrumbItem[] {
  return [
    { name: "排課首頁", url: `${SITE_ORIGIN}/` },
    { name: GUIDE_INDEX.title, url: guideIndexUrl() },
  ];
}

/** 首頁 → 選課指南 → 該子頁。 */
export function guidePageBreadcrumb(page: GuidePageMeta): BreadcrumbItem[] {
  return [...guideIndexBreadcrumb(), { name: page.title, url: guideUrl(page.slug) }];
}

/**
 * 指南子頁的 Article。`@id` 用 `#article` 與 layout 的 `#website` / `#publisher` 共存，
 * publisher/isPartOf 以 @id 參照 layout 那份 graph（同一頁上都在，不重複展開）。
 */
export function buildGuideArticleJsonLd(page: GuidePageMeta): Record<string, unknown> {
  const url = guideUrl(page.slug);
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    "@id": `${url}#article`,
    url,
    headline: page.heading,
    description: page.description,
    inLanguage: "zh-Hant",
    isPartOf: { "@id": `${SITE_ORIGIN}/#website` },
    publisher: { "@id": `${SITE_ORIGIN}/#publisher` },
    author: { "@id": `${SITE_ORIGIN}/#publisher` },
    about: NTUT,
    // 本站是第三方整理者；制度規則的權威在校方公告。這句和站內揭露文字一致。
    disambiguatingDescription:
      "本站為獨立開發的非官方工具，與國立臺北科技大學無隸屬或合作關係。本頁為第三方整理的說明，制度細節一律以學校公告為準。",
  };
}
