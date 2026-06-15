import { describe, it, expect } from "vitest";
import { resolveMatric, libraryBadge, GROUP_BADGE } from "./matric";
import type { CourseOffering } from "@/lib/data/types";

const make = (over: Partial<CourseOffering>): CourseOffering =>
  ({ offering_id: "x", name: { zh: "課" }, meetings: [], classes: [], teachers: [], ...over } as unknown as CourseOffering);

describe("resolveMatric", () => {
  it("prefers first-class matric_division when present", () => {
    const c = make({ matric_division: { code: "A", label: "進修部碩士在職專班", system: "on_job" } as never });
    expect(resolveMatric(c)).toMatchObject({ code: "A", label: "進修部碩士在職專班", system: "on_job", group: "grad_onjob" });
  });

  it("falls back to raw_fields.matric_codes when matric_division is absent", () => {
    const c = make({ raw_fields: { matric_codes: "7" } as never });
    expect(resolveMatric(c)).toMatchObject({ code: "7", label: "日四技", system: "day", group: "day_ug" });
  });

  it("multi-code: day system wins over others (體系優先)", () => {
    const c = make({ raw_fields: { matric_codes: "A,7" } as never }); // on_job + day → day
    expect(resolveMatric(c)?.code).toBe("7");
    expect(resolveMatric(c)?.group).toBe("day_ug");
  });

  it("multi-code: 碩博合開取碼字典序最小（8 碩士）", () => {
    const c = make({ raw_fields: { matric_codes: "9,8" } as never });
    expect(resolveMatric(c)).toMatchObject({ code: "8", label: "碩士", group: "grad_day" });
  });

  it("multi-code within on_job: lexicographically smallest code (A before D)", () => {
    const c = make({ raw_fields: { matric_codes: "D,A" } as never });
    expect(resolveMatric(c)).toMatchObject({ code: "A", group: "grad_onjob" });
  });

  it("unknown code → system/group other, label = raw code, no fallback default", () => {
    const c = make({ raw_fields: { matric_codes: "Z" } as never });
    expect(resolveMatric(c)).toMatchObject({ code: "Z", label: "Z", system: "other", group: "other" });
  });

  it("known code beats unknown", () => {
    const c = make({ raw_fields: { matric_codes: "Z,F" } as never });
    expect(resolveMatric(c)?.code).toBe("F");
  });

  it("no matric codes → null", () => {
    expect(resolveMatric(make({ raw_fields: {} as never }))).toBeNull();
    expect(resolveMatric(make({}))).toBeNull();
  });
});

describe("libraryBadge (學制感知)", () => {
  it("未選學制 → 每組都標（含日間部大學部）", () => {
    expect(libraryBadge("day_ug", null)).toEqual(GROUP_BADGE.day_ug);
    expect(libraryBadge("grad_day", null)).toEqual(GROUP_BADGE.grad_day);
    expect(libraryBadge("grad_onjob", null)).toEqual(GROUP_BADGE.grad_onjob);
  });
  it("選了學制 → 本學制不標、非本學制才標", () => {
    expect(libraryBadge("grad_day", "grad_day")).toBeNull();       // 本學制
    expect(libraryBadge("day_ug", "grad_day")).toEqual(GROUP_BADGE.day_ug);   // 碩士生看大學部 → 標
    expect(libraryBadge("grad_onjob", "grad_day")).toEqual(GROUP_BADGE.grad_onjob);
  });
  it("徽章短名正確", () => {
    expect(GROUP_BADGE.day_ug.label).toBe("日間部");
    expect(GROUP_BADGE.grad_onjob.label).toBe("在職");
  });
});
