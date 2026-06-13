import { describe, it, expect } from "vitest";
import { collegeOf, UNCLASSIFIED } from "./college-map";

describe("collegeOf", () => {
  it("maps known unit codes to their college", () => {
    expect(collegeOf("30")).toBe("機電學院");   // 機械
    expect(collegeOf("59")).toBe("電資學院");   // 資工
    expect(collegeOf("37")).toBe("管理學院");   // 工管
    expect(collegeOf("38")).toBe("設計學院");   // 工設
  });
  it("unmapped unit code → 未分類 (no throw, no dropped course)", () => {
    expect(collegeOf("ZZ")).toBe(UNCLASSIFIED);
    expect(collegeOf(null)).toBe(UNCLASSIFIED);
  });
});
