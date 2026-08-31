import { describe, expect, it } from "vitest";
import { buildCourseNoscriptHtml } from "./course-noscript";

const detail = {
  name: { zh: "國文", en: "Chinese" },
  course_code: "2A00001",
  offering_id: "360744",
  description: { zh: "本課程凡十六學分，供學生前四年修習之用。" },
  syllabi: [
    {
      teacher_name: "徐敏媛",
      outline: "以能力及素養之培植為導向",
      assessment: "平時30% 期中15% 期末20%",
      materials: "司馬遷：《史記》",
    },
  ],
};
const catalog = {
  credits: "2.0",
  unit_name: "智動科",
  teachers: [{ name: "徐敏媛" }],
  classrooms: [{ name: "六教526(e)" }],
};

describe("buildCourseNoscriptHtml", () => {
  it("emits the course facts an AI crawler needs", () => {
    const h = buildCourseNoscriptHtml(detail, "115-1", catalog)!;
    expect(h).toContain("<h1>國文（Chinese）</h1>");
    expect(h).toContain("115-1");
    expect(h).toContain("授課教師：徐敏媛");
    expect(h).toContain("開課單位：智動科");
    expect(h).toContain("教室：六教526(e)");
    expect(h).toContain("課號：360744");
    expect(h).toContain("以能力及素養之培植為導向");
    expect(h).toContain("平時30%");
  });

  it("carries the non-official disclosure", () => {
    const h = buildCourseNoscriptHtml(detail, "115-1", catalog)!;
    expect(h).toContain("非官方");
    expect(h).toContain("正式選課以學校系統為準");
  });

  it("escapes HTML so course text cannot break out of the markup", () => {
    const evil = { ...detail, name: { zh: '<script>alert(1)</script>' } };
    const h = buildCourseNoscriptHtml(evil, "115-1", catalog)!;
    expect(h).not.toContain("<script>");
    expect(h).toContain("&lt;script&gt;");
  });

  it("works without catalog info (detail only)", () => {
    const h = buildCourseNoscriptHtml(detail, "115-1")!;
    expect(h).toContain("國文");
    expect(h).toContain("授課教師：徐敏媛"); // fallback 到 syllabi 的 teacher_name
  });

  it("omits sections the data does not have", () => {
    const sparse = { name: { zh: "某課" } };
    const h = buildCourseNoscriptHtml(sparse, "115-1")!;
    expect(h).toContain("某課");
    expect(h).not.toContain("課程概述");
    expect(h).not.toContain("評量方式");
  });

  it("returns null without a course name", () => {
    expect(buildCourseNoscriptHtml({}, "115-1")).toBeNull();
  });

  it("clips very long text instead of dumping the whole syllabus", () => {
    const long = { ...detail, syllabi: [{ outline: "字".repeat(3000) }] };
    const h = buildCourseNoscriptHtml(long, "115-1")!;
    expect(h.length).toBeLessThan(3000);
    expect(h).toContain("…");
  });
});
