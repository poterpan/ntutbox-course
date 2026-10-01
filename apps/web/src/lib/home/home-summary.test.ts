import { describe, expect, it } from "vitest";
import type { CourseOffering } from "@/lib/data/types";
import { buildHomeSummary } from "./home-summary";

function course(p: Record<string, unknown> & { offering_id: string }): CourseOffering {
  return { term_key: "115-1", name: { zh: `課-${p.offering_id}` }, ...p } as unknown as CourseOffering;
}

/** unit 59 資工 3 門、36 機械 2 門、AA 通識 2 門（+1 門佔位課不算）、2B 1 門 */
const COURSES = [
  course({ offering_id: "1", unit_code: "59", unit_name: "資工系" }),
  course({ offering_id: "2", unit_code: "59", unit_name: "資工系" }),
  course({ offering_id: "3", unit_code: "59", unit_name: "資工系" }),
  course({ offering_id: "4", unit_code: "36", unit_name: "機械系" }),
  course({ offering_id: "5", unit_code: "36", unit_name: "機械系" }),
  course({ offering_id: "6", unit_code: "AA", unit_name: "通識中心" }),
  course({ offering_id: "7", unit_code: "AA", unit_name: "通識中心" }),
  course({ offering_id: "8", unit_code: "AA", unit_name: "通識中心", is_placeholder: true }),
  course({ offering_id: "9", unit_code: "2B", unit_name: "電子所" }),
];

const HUB = { termKey: "115-1", courses: COURSES, checkedAt: "2026-10-01T07:24:45+08:00" };

describe("buildHomeSummary", () => {
  it("課程數／單位數與 /browse/ 一致（排除佔位課）", () => {
    const s = buildHomeSummary({ hub: HUB, rooms: null });
    expect(s.termKey).toBe("115-1");
    expect(s.courseCount).toBe(8);
    expect(s.unitCount).toBe(4);
  });

  it("熱門系所依課程數遞減、同數依名稱，取前 topN，連結用 hub slug", () => {
    const s = buildHomeSummary({ hub: HUB, rooms: null, topN: 3 });
    expect(s.topUnits).toEqual([
      { slug: "59", unitName: "資工系", courseCount: 3 },
      { slug: "aa", unitName: "通識中心", courseCount: 2 },
      { slug: "36", unitName: "機械系", courseCount: 2 },
    ].sort((a, b) => b.courseCount - a.courseCount || (a.unitName < b.unitName ? -1 : 1)));
    expect(s.topUnits).toHaveLength(3);
  });

  it("預設取 12 個；單位不足就全給", () => {
    expect(buildHomeSummary({ hub: HUB, rooms: null }).topUnits).toHaveLength(4);
  });

  it("資料更新時間格式化成台北時間；沒有就 null", () => {
    expect(buildHomeSummary({ hub: HUB, rooms: null }).updatedAt).toBe("2026-10-01 07:24");
    expect(buildHomeSummary({ hub: { ...HUB, checkedAt: null }, rooms: null }).updatedAt).toBeNull();
  });

  it("教室：帶學期與間數；沒有教室資料 → null（不顯示，不捏造 0）", () => {
    const s = buildHomeSummary({ hub: HUB, rooms: { termKey: "115-1", rooms: [{}, {}, {}] } });
    expect(s.roomTermKey).toBe("115-1");
    expect(s.roomCount).toBe(3);
    const none = buildHomeSummary({ hub: HUB, rooms: null });
    expect(none.roomTermKey).toBeNull();
    expect(none.roomCount).toBeNull();
  });
});
