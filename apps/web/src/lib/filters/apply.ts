import type { CourseOffering } from "@/lib/data/types";
import type { FilterState } from "./types";
import { isEmi } from "./emi";
import { collegeOf } from "./college-map";

// Each active category is an AND clause; within a category, OR over its values.
export function applyFilters(courses: CourseOffering[], f: FilterState): CourseOffering[] {
  return courses.filter((c) => {
    if (f.weekdays.length && !(c.meetings ?? []).some((m) => f.weekdays.includes(m.day))) return false;
    if (f.periods.length && !(c.meetings ?? []).some((m) => m.periods.some((p) => f.periods.includes(p)))) return false;
    if (f.units.length && !(c.unit_code && f.units.includes(c.unit_code))) return false;
    if (f.colleges.length && !f.colleges.includes(collegeOf(c.unit_code))) return false;
    if (f.classes.length && !(c.classes ?? []).some((k) => f.classes.includes(k.code))) return false;
    if (f.emiOnly && !isEmi(c.language)) return false;
    return true;
  });
}
