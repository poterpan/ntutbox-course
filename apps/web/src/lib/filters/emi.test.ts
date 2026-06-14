import { describe, it, expect } from "vitest";
import { isEmi } from "./emi";

describe("isEmi", () => {
  it("treats English/EMI markers as EMI", () => {
    expect(isEmi("英文授課")).toBe(true);
    expect(isEmi("全英語")).toBe(true);
    expect(isEmi("English")).toBe(true);
    expect(isEmi("中英")).toBe(true);
    expect(isEmi("EMI")).toBe(true);
  });
  it("non-English / null → not EMI", () => {
    expect(isEmi("中文")).toBe(false);
    expect(isEmi(null)).toBe(false);
    expect(isEmi("")).toBe(false);
  });
});
