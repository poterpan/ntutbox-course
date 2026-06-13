import { describe, it, expect } from "vitest";
import { normalize, bigrams } from "./normalize";

describe("normalize", () => {
  it("NFKC folds full-width, lowercases, strips whitespace", () => {
    expect(normalize("　資料 結構 ＡＢＣ")).toBe("資料結構abc");
    expect(normalize("Data Structures")).toBe("datastructures");
  });
  it("handles null/empty", () => {
    expect(normalize("")).toBe("");
    expect(normalize(null)).toBe("");
  });
});

describe("bigrams", () => {
  it("produces overlapping 2-grams", () => {
    expect([...bigrams("資料結構")]).toEqual(["資料", "料結", "結構"]);
  });
  it("single char falls back to the unigram", () => {
    expect([...bigrams("林")]).toEqual(["林"]);
  });
  it("empty -> empty set", () => {
    expect(bigrams("").size).toBe(0);
  });
});
