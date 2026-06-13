import { describe, it, expect } from "vitest";
import { applyFilters } from "./apply";
import { EMPTY_FILTER } from "./types";
import type { CourseOffering } from "@/lib/data/types";

const mk = (o: Partial<CourseOffering>): CourseOffering => ({
  offering_id: "x", name: { zh: "課" }, meetings: [], classes: [], teachers: [],
  ...o,
} as unknown as CourseOffering);

const monP3 = mk({ offering_id: "a", unit_code: "59", language: "中文",
  meetings: [{ day: 1, periods: ["3", "4"] }] as never, classes: [{ code: "2652", name: "資工五", kind: "regular" }] as never });
const wedP5 = mk({ offering_id: "b", unit_code: "37", language: "英文授課",
  meetings: [{ day: 3, periods: ["5"] }] as never, classes: [{ code: "9999", name: "工管三", kind: "regular" }] as never });

describe("applyFilters", () => {
  it("empty filter passes everything", () => {
    expect(applyFilters([monP3, wedP5], EMPTY_FILTER)).toHaveLength(2);
  });
  it("intra-category OR: weekdays [1,3] keeps both", () => {
    expect(applyFilters([monP3, wedP5], { ...EMPTY_FILTER, weekdays: [1, 3] })).toHaveLength(2);
  });
  it("cross-category AND: weekday=1 AND unit=59 keeps only a", () => {
    const r = applyFilters([monP3, wedP5], { ...EMPTY_FILTER, weekdays: [1], units: ["59"] });
    expect(r.map((c) => c.offering_id)).toEqual(["a"]);
  });
  it("period filter matches any meeting period", () => {
    expect(applyFilters([monP3, wedP5], { ...EMPTY_FILTER, periods: ["5"] }).map((c) => c.offering_id)).toEqual(["b"]);
  });
  it("emiOnly keeps only English-taught", () => {
    expect(applyFilters([monP3, wedP5], { ...EMPTY_FILTER, emiOnly: true }).map((c) => c.offering_id)).toEqual(["b"]);
  });
  it("class filter matches by class code", () => {
    expect(applyFilters([monP3, wedP5], { ...EMPTY_FILTER, classes: ["2652"] }).map((c) => c.offering_id)).toEqual(["a"]);
  });
});
