import { describe, it, expect } from "vitest";
import { buildIndex } from "./build-index";
import type { CourseOffering } from "@/lib/data/types";

const course = {
  offering_id: "360712", course_code: "2B05003",
  name: { zh: "資料結構", en: "Data Structures" },
  teachers: [{ code: "1", name: "王老師" }],
  unit_code: "59", unit_name: "資工", notes_raw: "限資工系",
  classes: [{ code: "2652", name: "資工五", kind: "regular" }],
} as unknown as CourseOffering;

describe("buildIndex", () => {
  it("creates one SearchDoc per course with normalized blob + keys", () => {
    const docs = buildIndex([course]);
    expect(docs).toHaveLength(1);
    const d = docs[0];
    expect(d.offeringId).toBe("360712");
    expect(d.codeKeys).toContain("360712");
    expect(d.codeKeys).toContain("2b05003");
    expect(d.nameKey).toBe("資料結構");
    expect(d.blob).toContain("資料結構");
    expect(d.blob).toContain("datastructures");
    expect(d.blob).toContain("王老師");
    expect(d.blob).toContain("資工");
    expect(d.bigrams.has("資料")).toBe(true);
  });
});
