import { describe, expect, it } from "vitest";
import { GUIDE_PAGES, guidePageBySlug, guideUrl } from "./pages";
import {
  buildBreadcrumbJsonLd,
  buildGuideArticleJsonLd,
  guideIndexBreadcrumb,
  guidePageBreadcrumb,
} from "./schema";

describe("buildBreadcrumbJsonLd", () => {
  it("position 從 1 遞增，每項帶 name 與絕對 URL", () => {
    const ld = buildBreadcrumbJsonLd(guidePageBreadcrumb(guidePageBySlug("timetable")));
    expect(ld["@type"]).toBe("BreadcrumbList");
    const items = ld.itemListElement as Record<string, unknown>[];
    expect(items.map((i) => i.position)).toEqual([1, 2, 3]);
    expect(items[0].item).toBe("https://course.ntutbox.com/");
    expect(items[1].item).toBe("https://course.ntutbox.com/guide/");
    expect(items[2].item).toBe("https://course.ntutbox.com/guide/timetable/");
    for (const item of items) {
      expect(String(item.item).startsWith("https://")).toBe(true);
      expect(item.name).not.toBe("");
    }
  });

  it("hub 的麵包屑只有兩層", () => {
    const items = guideIndexBreadcrumb();
    expect(items).toHaveLength(2);
  });
});

describe("buildGuideArticleJsonLd", () => {
  it("每頁都產出可用的 Article，@id 與 url 對應該頁", () => {
    for (const page of GUIDE_PAGES) {
      const ld = buildGuideArticleJsonLd(page);
      expect(ld["@type"]).toBe("Article");
      expect(ld.url).toBe(guideUrl(page.slug));
      expect(ld["@id"]).toBe(`${guideUrl(page.slug)}#article`);
      expect(ld.headline).toBe(page.heading);
      expect(ld.inLanguage).toBe("zh-Hant");
    }
  });

  it("publisher / isPartOf 以 @id 參照 layout 那份 graph，不重複展開", () => {
    const ld = buildGuideArticleJsonLd(guidePageBySlug("selection-phases"));
    expect(ld.isPartOf).toEqual({ "@id": "https://course.ntutbox.com/#website" });
    expect(ld.publisher).toEqual({ "@id": "https://course.ntutbox.com/#publisher" });
  });

  it("about 指向學校（制度權威在校方），不是把本站標成來源", () => {
    const ld = buildGuideArticleJsonLd(guidePageBySlug("general-education")) as {
      about: Record<string, string>;
    };
    expect(ld.about["@type"]).toBe("CollegeOrUniversity");
    expect(ld.about.name).toBe("國立臺北科技大學");
    expect(ld.about.url).toContain("ntut.edu.tw");
  });

  it("帶非官方揭露，且不含 dateModified（沒有可信時間戳就不標）", () => {
    const ld = buildGuideArticleJsonLd(guidePageBySlug("micro-programs"));
    expect(String(ld.disambiguatingDescription)).toContain("非官方");
    expect(String(ld.disambiguatingDescription)).toContain("以學校公告為準");
    expect(ld.dateModified).toBeUndefined();
    expect(ld.datePublished).toBeUndefined();
  });

  /**
   * 稽核明確要求：FAQPage 已於 2026-05 被 Google 移除 SERP 特性，不得為效益新增；
   * QAPage 只適用真實的使用者問答頁。這條防止日後有人把它們加回來。
   */
  it("不產出 FAQPage / QAPage / HowTo", () => {
    const all = GUIDE_PAGES.map((p) => JSON.stringify(buildGuideArticleJsonLd(p))).join("");
    expect(all).not.toContain("FAQPage");
    expect(all).not.toContain("QAPage");
    expect(all).not.toContain("HowTo");
  });
});
