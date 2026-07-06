import { describe, it, expect } from "vitest";
import { buildCourseSitemapXml, latestTermKey } from "./course-sitemap";

describe("latestTermKey", () => {
  it("picks the numerically-latest term (per segment, not lexicographic)", () => {
    expect(latestTermKey(["110-1", "110-2", "115-1", "114-2"])).toBe("115-1");
    expect(latestTermKey(["99-2", "100-1"])).toBe("100-1");
  });

  it("ignores malformed keys; empty → null", () => {
    expect(latestTermKey(["bogus", "115-1"])).toBe("115-1");
    expect(latestTermKey([])).toBeNull();
    expect(latestTermKey(["bogus"])).toBeNull();
  });
});

describe("buildCourseSitemapXml", () => {
  it("emits one <url> per course with XML-escaped share link", () => {
    const xml = buildCourseSitemapXml("https://course.ntutbox.com", "115-1", {
      "360744": "國文",
      "360745": "英文",
    });
    expect(xml).toContain('<?xml version="1.0" encoding="UTF-8"?>');
    expect(xml).toContain('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">');
    // & between query params must be XML-escaped
    expect(xml).toContain(
      "<url><loc>https://course.ntutbox.com/?term=115-1&amp;course=360744</loc></url>",
    );
    expect(xml.match(/<url>/g)).toHaveLength(2);
    expect(xml).not.toContain("term=115-1&course="); // no raw ampersand
  });

  it("empty names → empty urlset", () => {
    const xml = buildCourseSitemapXml("https://course.ntutbox.com", "115-1", {});
    expect(xml).not.toContain("<url>");
    expect(xml).toContain("</urlset>");
  });
});
