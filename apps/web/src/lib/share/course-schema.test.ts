import { describe, expect, it } from "vitest";
import { buildCourseJsonLd } from "./course-schema";
import type { CourseOffering } from "@/lib/data/types";

const base = {
  offering_id: "360744",
  course_code: "2A00001",
  name: { zh: "國文", en: "Chinese" },
  credits: "2.0",
  unit_name: "智動科",
  teachers: [{ code: "23602", name: "徐敏媛" }],
  classrooms: [{ code: "438", name: "六教526(e)" }],
} as unknown as CourseOffering;

describe("buildCourseJsonLd", () => {
  it("maps the core course fields", () => {
    const ld = buildCourseJsonLd({ course: base, termKey: "115-1" })!;
    expect(ld["@type"]).toBe("Course");
    expect(ld.name).toBe("國文");
    expect(ld.alternateName).toBe("Chinese");
    expect(ld.courseCode).toBe("2A00001");
    expect(ld.numberOfCredits).toBe(2);
    expect(ld.url).toContain("?term=115-1&course=360744");
  });

  it("attributes provider to the university, never to this site", () => {
    const ld = buildCourseJsonLd({ course: base, termKey: "115-1" })!;
    const provider = ld.provider as Record<string, unknown>;
    expect(provider.name).toBe("國立臺北科技大學");
    expect(JSON.stringify(ld)).not.toContain("北科盒子");
  });

  it("carries instructor and location into the CourseInstance", () => {
    const ld = buildCourseJsonLd({ course: base, termKey: "115-1" })!;
    const inst = ld.hasCourseInstance as Record<string, unknown>;
    expect(inst.courseMode).toBe("onsite");
    expect(inst.instructor).toEqual([{ "@type": "Person", name: "徐敏媛" }]);
    expect(inst.location).toEqual([{ "@type": "Place", name: "六教526(e)" }]);
  });

  it("omits fields the data does not have rather than inventing them", () => {
    const sparse = { offering_id: "1", name: { zh: "某課" } } as unknown as CourseOffering;
    const ld = buildCourseJsonLd({ course: sparse, termKey: "115-1" })!;
    expect(ld.courseCode).toBeUndefined();
    expect(ld.numberOfCredits).toBeUndefined();
    expect(ld.department).toBeUndefined();
    expect((ld.hasCourseInstance as Record<string, unknown>).instructor).toBeUndefined();
    expect((ld.hasCourseInstance as Record<string, unknown>).courseMode).toBeUndefined();
  });

  it("does not put department on Course (schema.org: Organization-only property)", () => {
    const ld = buildCourseJsonLd({ course: base, termKey: "115-1" })!;
    expect(ld.department).toBeUndefined();
    // 系所沒有消失，是改掛到 provider（Organization）底下才符合 schema.org 型別
    const provider = ld.provider as Record<string, unknown>;
    expect(provider["@type"]).toBe("CollegeOrUniversity");
    expect((provider.department as Record<string, unknown>).name).toBe("智動科");
  });

  it("omits numberOfCredits for fractional credits (schema.org wants Integer)", () => {
    // 實際資料有 0.5 學分課（115-1 的 365648／366444 專題討論）
    const halfCredit = { ...base, credits: "0.5" } as unknown as CourseOffering;
    const ld = buildCourseJsonLd({ course: halfCredit, termKey: "115-1" })!;
    expect(ld.numberOfCredits).toBeUndefined();
  });

  it("keeps integer credits as a plain number", () => {
    const ld = buildCourseJsonLd({ course: base, termKey: "115-1" })!;
    expect(ld.numberOfCredits).toBe(2);
  });

  it("returns null without a course name", () => {
    expect(buildCourseJsonLd({ course: { offering_id: "1" } as unknown as CourseOffering, termKey: "115-1" })).toBeNull();
  });
});
