import { describe, expect, it } from "vitest";
import {
  GUIDE_INDEX,
  GUIDE_PAGES,
  GUIDE_PATH,
  guideIndexUrl,
  guideMetadata,
  guidePageBySlug,
  guidePath,
  guideUrl,
  otherGuidePages,
} from "./pages";

describe("guide pages registry", () => {
  it("所有路徑都帶結尾斜線（next.config.ts trailingSlash: true）", () => {
    expect(GUIDE_PATH).toBe("/guide/");
    for (const page of GUIDE_PAGES) {
      expect(guidePath(page.slug)).toBe(`/guide/${page.slug}/`);
      expect(guidePath(page.slug).endsWith("/")).toBe(true);
      expect(guideUrl(page.slug)).toBe(`https://course.ntutbox.com/guide/${page.slug}/`);
    }
    expect(guideIndexUrl()).toBe("https://course.ntutbox.com/guide/");
  });

  it("slug 不重複、每頁都有 title/heading/description/answers", () => {
    const slugs = GUIDE_PAGES.map((p) => p.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
    for (const page of GUIDE_PAGES) {
      expect(page.title.length).toBeGreaterThan(6);
      expect(page.heading.length).toBeGreaterThan(6);
      // description 進 meta description，太短沒資訊、太長會被截斷。
      expect(page.description.length).toBeGreaterThan(40);
      expect(page.description.length).toBeLessThan(160);
      expect(page.answers).not.toBe("");
    }
    expect(GUIDE_INDEX.description.length).toBeGreaterThan(40);
  });

  it("title 不重複塞站名（layout 的 %s｜北科盒子 排課 模板會加）", () => {
    for (const page of GUIDE_PAGES) {
      expect(page.title).not.toContain("北科盒子");
    }
  });

  /**
   * ⚠️ 這條是整組指南頁能不能被索引的關鍵：root layout 把 canonical 釘在 "/"，
   * 子路由沒覆蓋就會全部 canonical 到首頁。曾經是稽核指出的實際風險。
   */
  it("guideMetadata 一定覆蓋 canonical 成自己的路徑", () => {
    for (const page of GUIDE_PAGES) {
      const meta = guideMetadata(page);
      expect(meta.alternates?.canonical).toBe(`/guide/${page.slug}/`);
      expect(meta.title).toBe(page.title);
      expect(meta.description).toBe(page.description);
      expect(meta.openGraph?.url).toBe(`/guide/${page.slug}/`);
    }
  });

  it("otherGuidePages 排除自己、且不漏其他頁", () => {
    for (const page of GUIDE_PAGES) {
      const others = otherGuidePages(page.slug);
      expect(others).toHaveLength(GUIDE_PAGES.length - 1);
      expect(others.some((p) => p.slug === page.slug)).toBe(false);
    }
  });

  it("guidePageBySlug 找不到時丟錯，不回 undefined 讓頁面靜默壞掉", () => {
    expect(guidePageBySlug("timetable").slug).toBe("timetable");
    // @ts-expect-error 故意傳不存在的 slug
    expect(() => guidePageBySlug("nope")).toThrow();
  });
});
