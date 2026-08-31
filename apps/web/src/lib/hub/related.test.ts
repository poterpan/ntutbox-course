import { describe, expect, it } from "vitest";
import type { CourseOffering } from "@/lib/data/types";
import { buildRelated, DEFAULT_RELATED_LIMITS } from "./related";

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

const T = (name: string) => ({ code: name, name });

describe("buildRelated", () => {
  it("finds other sections of the same course_code", () => {
    const self = course({ offering_id: "100", course_code: "X1", unit_code: "36" });
    const all = [self, course({ offering_id: "101", course_code: "X1", unit_code: "36" })];
    const g = buildRelated(self, all);
    expect(g[0].title).toBe("同課其他班");
    expect(g[0].items.map((i) => i.offeringId)).toEqual(["101"]);
  });

  it("finds other courses taught by the same teacher", () => {
    const self = course({ offering_id: "100", course_code: "X1", teachers: [T("王小明")] });
    const other = course({ offering_id: "200", course_code: "X2", teachers: [T("王小明")] });
    const g = buildRelated(self, [self, other]);
    expect(g.map((x) => x.title)).toContain("同教師其他課");
    expect(g.find((x) => x.title === "同教師其他課")!.items.map((i) => i.offeringId)).toEqual(["200"]);
  });

  it("falls back to same-unit courses so every course has at least one outbound link", () => {
    // 沒有兄弟班、沒有掛教師的課也必須連得出去，否則它在圖上仍是孤島。
    const self = course({ offering_id: "100", course_code: "X1", unit_code: "36", unit_name: "電子系" });
    const other = course({ offering_id: "200", course_code: "X2", unit_code: "36", unit_name: "電子系" });
    const g = buildRelated(self, [self, other]);
    expect(g).toHaveLength(1);
    expect(g[0].title).toBe("電子系 其他課程");
    expect(g[0].items.map((i) => i.offeringId)).toEqual(["200"]);
  });

  it("never links to itself or to placeholder offerings", () => {
    const self = course({ offering_id: "100", course_code: "X1", unit_code: "36" });
    const all = [
      self,
      course({ offering_id: "101", course_code: "X1", unit_code: "36", is_placeholder: true }),
    ];
    expect(buildRelated(self, all)).toEqual([]);
  });

  it("does not repeat a course across groups", () => {
    // 同一堂課同時符合「同課其他班」與「同單位其他課」時只出現一次——重複連結是雜訊。
    const self = course({ offering_id: "100", course_code: "X1", unit_code: "36", teachers: [T("王")] });
    const twin = course({ offering_id: "101", course_code: "X1", unit_code: "36", teachers: [T("王")] });
    const g = buildRelated(self, [self, twin]);
    const ids = g.flatMap((x) => x.items.map((i) => i.offeringId));
    expect(ids).toEqual(["101"]);
  });

  it("caps each group so a pool course does not emit hundreds of links", () => {
    // 實測 115-1 有 course_code 掛到 176 個班次（體育/通識 pool 課）。
    const self = course({ offering_id: "1000", course_code: "P", unit_code: "10" });
    const all = [self, ...Array.from({ length: 176 }, (_, i) => course({ offering_id: `2${String(i).padStart(3, "0")}`, course_code: "P", unit_code: "10" }))];
    const g = buildRelated(self, all);
    expect(g[0].items).toHaveLength(DEFAULT_RELATED_LIMITS.sameCode);
    const total = g.reduce((n, x) => n + x.items.length, 0);
    expect(total).toBeLessThanOrEqual(
      DEFAULT_RELATED_LIMITS.sameCode + DEFAULT_RELATED_LIMITS.sameTeacher + DEFAULT_RELATED_LIMITS.sameUnit,
    );
  });

  it("spreads inbound links over the whole group instead of piling them on the first few", () => {
    // 若改成「取前 N 個」，排序在後的課一條 inbound 都收不到 = 孤島換個形式再現。
    const ids = Array.from({ length: 20 }, (_, i) => `3${String(i).padStart(3, "0")}`);
    const all = ids.map((id) => course({ offering_id: id, course_code: "S", unit_code: "36" }));
    const inbound = new Map(ids.map((id) => [id, 0]));
    for (const c of all) {
      for (const grp of buildRelated(c, all, { sameCode: 4, sameTeacher: 0, sameUnit: 0 })) {
        for (const it of grp.items) inbound.set(it.offeringId, inbound.get(it.offeringId)! + 1);
      }
    }
    expect(Math.min(...inbound.values())).toBeGreaterThan(0); // 沒有任何一課是零 inbound
    expect([...new Set(inbound.values())]).toEqual([4]);      // 而且完全均勻
  });

  it("carries the fields a link row needs to be identifiable", () => {
    const self = course({ offering_id: "100", course_code: "X1" });
    const other = course({
      offering_id: "101",
      course_code: "X1",
      credits: 3,
      unit_name: "電子系",
      teachers: [T("王小明")],
      classes: [{ code: "2891", name: "電子四甲" }],
      meetings: [{ day: 2, periods: ["1", "2"] }],
    });
    const [g] = buildRelated(self, [self, other]);
    expect(g.items[0]).toEqual({
      offeringId: "101",
      name: "課-101",
      teachers: "王小明",
      classes: "電子四甲",
      schedule: "週二 1、2節",
      unitName: "電子系",
      credits: "3",
    });
  });

  it("is deterministic for the same input", () => {
    const self = course({ offering_id: "100", course_code: "X1", unit_code: "36" });
    const all = [self, ...["105", "101", "103"].map((id) => course({ offering_id: id, course_code: "X1", unit_code: "36" }))];
    const a = JSON.stringify(buildRelated(self, all));
    const b = JSON.stringify(buildRelated(self, [...all].reverse()));
    expect(a).toBe(b);
  });
});
