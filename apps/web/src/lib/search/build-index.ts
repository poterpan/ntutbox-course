import type { CourseOffering } from "@/lib/data/types";
import { normalize, bigrams } from "./normalize";

export interface SearchDoc {
  offeringId: string;
  codeKeys: string[];   // normalized offering_id + course_code (for exact/prefix)
  nameKey: string;      // normalized zh name (for exact/prefix)
  blob: string;         // normalized concat of all searchable fields
  bigrams: Set<string>; // bigrams of blob
}

export function buildIndex(courses: CourseOffering[]): SearchDoc[] {
  return courses.map((c) => {
    const parts = [
      c.name?.zh, c.name?.en,
      ...(c.teachers ?? []).map((t) => t.name),
      c.offering_id, c.course_code ?? "",
      c.unit_name ?? "", c.unit_code ?? "",
      ...(c.classes ?? []).map((k) => k.name),
      c.notes_raw ?? "",
    ];
    const blob = parts.map(normalize).join("|");
    const codeKeys = [normalize(c.offering_id), normalize(c.course_code)].filter(Boolean);
    return {
      offeringId: c.offering_id,
      codeKeys,
      nameKey: normalize(c.name?.zh),
      blob,
      bigrams: bigrams(blob.replace(/\|/g, "")),
    };
  });
}
