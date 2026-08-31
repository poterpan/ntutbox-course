import { describe, expect, it } from "vitest";
import type { CourseOffering } from "@/lib/data/types";
import {
  buildUnitHubs,
  cyclicWindow,
  groupUnitsByKind,
  scheduleLabel,
  siblingUnits,
  teachersLabel,
  unitKindOf,
  unitSlug,
} from "./units";

// 測試 fixture 用寬鬆型別：只固定 offering_id，其餘欄位照各案例需要塞
// （CourseOffering 的巢狀 union 如 MatricSystem 會讓字面量推導失敗）。
function course(p: Record<string, unknown> & { offering_id: string }): CourseOffering {
  return {
    term_key: "115-1",
    name: { zh: `課-${p.offering_id}` },
    selection: { cwish_subj: p.offering_id },
    ...p,
  } as unknown as CourseOffering;
}

describe("unitSlug", () => {
  it("lowercases the unit code and keeps it URL-safe", () => {
    expect(unitSlug("36")).toBe("36");
    expect(unitSlug("2B")).toBe("2b");
    expect(unitSlug("AA")).toBe("aa");
  });
  it("strips characters that would break a path segment", () => {
    expect(unitSlug(" A/B ")).toBe("a-b");
    expect(unitSlug("!!")).toBe("unknown"); // 不回空字串——空 slug 會產出 /browse//
  });
});

describe("unitKindOf", () => {
  it("classifies by the Chinese name suffix (no external org chart needed)", () => {
    expect(unitKindOf("電子系")).toBe("dept");
    expect(unitKindOf("智動科")).toBe("dept");
    expect(unitKindOf("機電所")).toBe("graduate");
    expect(unitKindOf("半導體學士學位學程")).toBe("program");
    expect(unitKindOf("機電學士班")).toBe("program");
    expect(unitKindOf("科技法律學程")).toBe("program");
    expect(unitKindOf("機電學院")).toBe("other");
    expect(unitKindOf("通識中心")).toBe("other");
    expect(unitKindOf("體育室")).toBe("other");
  });
  it("puts 專班 in its own bucket even when the name also reads like a 系所", () => {
    // 「電資外國學生專班」尾綴是「專班」但字串裡有「電資」；不能被 dept/graduate 搶走。
    expect(unitKindOf("電資外國學生專班")).toBe("international");
    expect(unitKindOf("機械自動化外生專班")).toBe("international");
    expect(unitKindOf("機電科技博士外生專班")).toBe("international");
  });
});

describe("buildUnitHubs", () => {
  it("groups by unit_code and sorts courses by offering id (stable output across builds)", () => {
    const hubs = buildUnitHubs([
      course({ offering_id: "300002", unit_code: "36", unit_name: "電子系" }),
      course({ offering_id: "300001", unit_code: "36", unit_name: "電子系" }),
      course({ offering_id: "300003", unit_code: "14", unit_name: "通識中心" }),
    ]);
    expect(hubs.map((h) => h.slug)).toEqual(["14", "36"]);
    const ee = hubs.find((h) => h.slug === "36")!;
    expect(ee.unitName).toBe("電子系");
    expect(ee.courseCount).toBe(2);
    expect(ee.courses.map((c) => c.offeringId)).toEqual(["300001", "300002"]);
  });

  it("excludes placeholder offerings (「請選…」 stubs are not linkable courses)", () => {
    const hubs = buildUnitHubs([
      course({ offering_id: "1", unit_code: "36", unit_name: "電子系" }),
      course({ offering_id: "2", unit_code: "36", unit_name: "電子系", is_placeholder: true }),
    ]);
    expect(hubs[0].courses.map((c) => c.offeringId)).toEqual(["1"]);
  });

  it("keeps courses that have no unit_code instead of dropping them", () => {
    // 丟掉 = 那些課永遠沒有內部連結，正是本次要修的孤島問題。
    const hubs = buildUnitHubs([course({ offering_id: "9", unit_code: undefined, unit_name: undefined })]);
    expect(hubs).toHaveLength(1);
    expect(hubs[0].slug).toBe("unknown");
    expect(hubs[0].courses).toHaveLength(1);
  });

  it("gives every unit code a distinct slug even if two codes would collide", () => {
    const hubs = buildUnitHubs([
      course({ offering_id: "1", unit_code: "A-B", unit_name: "甲系" }),
      course({ offering_id: "2", unit_code: "A/B", unit_name: "乙系" }),
    ]);
    expect(new Set(hubs.map((h) => h.slug)).size).toBe(2);
  });

  it("maps the display fields a hub row needs", () => {
    const hubs = buildUnitHubs([
      course({
        offering_id: "300001",
        unit_code: "36",
        unit_name: "電子系",
        credits: 3,
        requirement: { symbol: "△", category: "required" },
        teachers: [{ code: "1", name: "王小明" }, { code: "2", name: "李小華" }],
        meetings: [{ day: 1, periods: ["3", "4"] }, { day: 3, periods: ["5"] }],
        matric_division: { code: "1", label: "日間部學士班", system: "day_ug" },
      }),
    ]);
    expect(hubs[0].courses[0]).toEqual({
      offeringId: "300001",
      name: "課-300001",
      credits: "3",
      requirement: "△",
      teachers: "王小明、李小華",
      schedule: "週一 3、4節；週三 5節",
      division: "日間部學士班",
    });
  });
});

describe("scheduleLabel / teachersLabel", () => {
  it("returns empty string when the source has nothing (never a fake default)", () => {
    expect(scheduleLabel(course({ offering_id: "1" }))).toBe("");
    expect(teachersLabel(course({ offering_id: "1" }))).toBe("");
  });
  it("drops blank teacher names", () => {
    const c = course({ offering_id: "1", teachers: [{ code: "1", name: null }, { code: "2", name: "王小明" }] });
    expect(teachersLabel(c)).toBe("王小明");
  });
});

describe("groupUnitsByKind", () => {
  it("sections units by kind, largest first, and omits empty sections", () => {
    const hubs = buildUnitHubs([
      course({ offering_id: "1", unit_code: "36", unit_name: "電子系" }),
      course({ offering_id: "2", unit_code: "36", unit_name: "電子系" }),
      course({ offering_id: "3", unit_code: "59", unit_name: "資工系" }),
      course({ offering_id: "4", unit_code: "40", unit_name: "機電所" }),
    ]);
    const sections = groupUnitsByKind(hubs);
    expect(sections.map((s) => s.kind)).toEqual(["dept", "graduate"]);
    expect(sections[0].units.map((u) => u.unitName)).toEqual(["電子系", "資工系"]); // 2 門 > 1 門
  });
});

describe("cyclicWindow", () => {
  it("wraps around so every element gets picked equally often", () => {
    const pool = ["a", "b", "c", "d"];
    expect(cyclicWindow(pool, 2, 3)).toEqual(["c", "d", "a"]);
    expect(cyclicWindow(pool, 0, 2)).toEqual(["a", "b"]);
  });
  it("never returns more than the pool holds, and tolerates edge inputs", () => {
    expect(cyclicWindow(["a", "b"], 0, 10)).toEqual(["a", "b"]);
    expect(cyclicWindow([], 0, 3)).toEqual([]);
    expect(cyclicWindow(["a"], 0, 0)).toEqual([]);
    expect(cyclicWindow(["a", "b", "c"], -1, 2)).toEqual(["c", "a"]);
  });

  it("distributes inbound links uniformly — no element is left orphaned", () => {
    // 這是 hub / 交叉連結的核心不變量：取「前 N 個」會讓排序在後的項目一條連結都收不到。
    const pool = ["a", "b", "c", "d", "e", "f"];
    const inbound = new Map(pool.map((x) => [x, 0]));
    pool.forEach((_, i) => {
      for (const picked of cyclicWindow(pool, i + 1, 2)) inbound.set(picked, inbound.get(picked)! + 1);
    });
    expect([...new Set(inbound.values())]).toEqual([2]);
  });
});

describe("siblingUnits", () => {
  it("links only to units of the same kind, excluding itself", () => {
    const hubs = buildUnitHubs([
      course({ offering_id: "1", unit_code: "36", unit_name: "電子系" }),
      course({ offering_id: "2", unit_code: "59", unit_name: "資工系" }),
      course({ offering_id: "3", unit_code: "40", unit_name: "機電所" }),
    ]);
    const sibs = siblingUnits(hubs, "36");
    expect(sibs.map((u) => u.unitName)).toEqual(["資工系"]);
  });
  it("returns nothing for an unknown slug", () => {
    expect(siblingUnits(buildUnitHubs([]), "nope")).toEqual([]);
  });
});
