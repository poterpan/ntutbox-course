import { describe, expect, it } from "vitest";
import { sanitizePage, sanitizeReferrer } from "./sanitize";

const ORIGIN = "https://course.ntutbox.com";

describe("sanitizePage", () => {
  it("drops plan / course / payload / token / code and any unknown param", () => {
    const page = sanitizePage(
      `${ORIGIN}/?term=115-1&plan=360744.360745&course=360744&payload=abc&token=t&code=c&whatever=1`,
    )!;
    expect(page.page_location).toBe(`${ORIGIN}/`);
    expect(page.page_path).toBe("/");
    // page_path 才是 query 的載體（origin 本身就含 "course"，不能拿 page_location 比對字串）。
    for (const leak of ["plan", "course", "payload", "token", "code", "whatever", "360744"]) {
      expect(page.page_path).not.toContain(leak);
    }
  });

  it("keeps allowlisted utm_* / click IDs and always strips the hash", () => {
    const page = sanitizePage(
      `${ORIGIN}/?utm_source=google&utm_medium=cpc&utm_campaign=1151_adddrop&gclid=abc-123_x.y~z#section`,
    )!;
    expect(page.page_location).toContain("utm_source=google");
    expect(page.page_location).toContain("utm_medium=cpc");
    expect(page.page_location).toContain("utm_campaign=1151_adddrop");
    expect(page.page_location).toContain("gclid=abc-123_x.y~z");
    expect(page.page_location).not.toContain("#");
  });

  it("turns a valid ?term into term_key and removes it from the URL", () => {
    const page = sanitizePage(`${ORIGIN}/?term=115-1`)!;
    expect(page.term_key).toBe("115-1");
    expect(page.page_location).toBe(`${ORIGIN}/`);
  });

  it("ignores a malformed ?term (no term_key, still stripped)", () => {
    for (const bad of ["115-3", "15-1", "115_1", "1151"]) {
      const page = sanitizePage(`${ORIGIN}/?term=${bad}`)!;
      expect(page.term_key).toBeUndefined();
      expect(page.page_location).toBe(`${ORIGIN}/`);
    }
  });

  it("discards over-long utm values instead of truncating them", () => {
    const ok = "a".repeat(128);
    const tooLong = "a".repeat(129);
    expect(sanitizePage(`${ORIGIN}/?utm_term=${ok}`)!.page_location).toContain(ok);
    expect(sanitizePage(`${ORIGIN}/?utm_term=${tooLong}`)!.page_location).toBe(`${ORIGIN}/`);
  });

  it("strips control characters from utm values", () => {
    const raw = `a${String.fromCharCode(10)}b${String.fromCharCode(0)}c`;
    const page = sanitizePage(`${ORIGIN}/?utm_source=${encodeURIComponent(raw)}`)!;
    expect(page.page_location).toContain("utm_source=abc");
  });

  it("rejects click IDs outside the allowed charset or over 512 chars", () => {
    expect(sanitizePage(`${ORIGIN}/?gclid=${encodeURIComponent("bad value!")}`)!.page_location).toBe(`${ORIGIN}/`);
    expect(sanitizePage(`${ORIGIN}/?gbraid=${"a".repeat(513)}`)!.page_location).toBe(`${ORIGIN}/`);
    expect(sanitizePage(`${ORIGIN}/?wbraid=${"a".repeat(512)}`)!.page_location).toContain("wbraid=");
  });

  it("keeps only origin + pathname of the referrer", () => {
    const page = sanitizePage(`${ORIGIN}/`, "https://www.google.com/search?q=%E5%8C%97%E7%A7%91%E9%81%B8%E8%AA%B2#top")!;
    expect(page.page_referrer).toBe("https://www.google.com/search");
  });

  it("omits page_referrer for an empty or non-http referrer", () => {
    expect(sanitizePage(`${ORIGIN}/`, "")!.page_referrer).toBeUndefined();
    expect(sanitizePage(`${ORIGIN}/`, "android-app://com.example")!.page_referrer).toBeUndefined();
    expect(sanitizeReferrer("not a url")).toBeUndefined();
  });

  it("returns null for a non-http(s) or unparsable location", () => {
    expect(sanitizePage("javascript:alert(1)")).toBeNull();
    expect(sanitizePage("nonsense")).toBeNull();
  });
});
