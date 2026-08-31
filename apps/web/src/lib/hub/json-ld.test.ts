import { describe, expect, it } from "vitest";
import { jsonLdText } from "./json-ld";

describe("jsonLdText", () => {
  it("keeps the JSON parseable", () => {
    expect(JSON.parse(jsonLdText({ a: 1, b: "x" }))).toEqual({ a: 1, b: "x" });
  });
  it("escapes '<' so crawled data can never close the <script> tag early", () => {
    const evil = "</scr" + "ipt><img onerror=alert(1)>";
    const out = jsonLdText({ name: evil });
    expect(out).not.toContain("</scr" + "ipt>");
    expect(out).toContain("\\u003c");
    expect(JSON.parse(out).name).toBe(evil);
  });
  it("escapes the JS-hostile line separators U+2028 / U+2029", () => {
    const raw = "a\u2028b\u2029c";
    const out = jsonLdText({ name: raw });
    expect(out).not.toContain("\u2028");
    expect(out).not.toContain("\u2029");
    expect(JSON.parse(out).name).toBe(raw);
  });
});
