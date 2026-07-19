import { describe, it, expect } from "vitest";
import { periodOrder, sortPeriods, periodLabel } from "./periods";
import type { PeriodTable } from "@/lib/data/types";

const table: PeriodTable = {
  schema_version: 2, timezone: "Asia/Taipei",
  periods: [
    { token: "1", order: 0, start_hm: "08:10", end_hm: "09:00", label: "1" },
    { token: "N", order: 4, start_hm: "12:10", end_hm: "13:00", label: "N" },
    { token: "5", order: 5, start_hm: "13:10", end_hm: "14:00", label: "5" },
    { token: "A", order: 10, start_hm: "18:30", end_hm: "19:20", label: "A" },
  ],
} as PeriodTable;

describe("periods", () => {
  it("periodOrder maps token → order (N before 5, A after 9)", () => {
    const ord = periodOrder(table);
    expect(ord.get("N")).toBe(4);
    expect(ord.get("5")).toBe(5);
    expect(ord.get("A")).toBe(10);
  });
  it("sortPeriods uses the non-1..14 ordering", () => {
    expect(sortPeriods(["5", "N", "1"], table)).toEqual(["1", "N", "5"]);
  });
  it("periodLabel returns display label", () => {
    expect(periodLabel("N", table)).toBe("N");
  });
});
