import type { CourseOffering } from "@/lib/data/types";
import type { FilterState } from "./types";
import { isEmi } from "./emi";
import { collegeOf } from "./college-map";

// Each active category is an AND clause; within a category, OR over its values.
// Weekday × period are a single time clause: when BOTH are active, one meeting
// must satisfy both (same day AND period) — not two different meetings.
// `mprogramOids` = 全微學程 offering_id 聯集（見 getProgramOidSet）；only=交集、exclude=差集。
// 集合未提供時 only/exclude 視同 all（防呆；UI 以 chip disabled 保證資料就緒才可切）。
export function applyFilters(
  courses: CourseOffering[],
  f: FilterState,
  mprogramOids?: ReadonlySet<string>,
): CourseOffering[] {
  return courses.filter((c) => {
    if (f.weekdays.length || f.periods.length) {
      const hit = (c.meetings ?? []).some((m) => {
        const dayOk = !f.weekdays.length || f.weekdays.includes(m.day);
        const periodOk = !f.periods.length || m.periods.some((p) => f.periods.includes(p));
        return dayOk && periodOk;
      });
      if (!hit) return false;
    }
    if (f.units.length && !(c.unit_code && f.units.includes(c.unit_code))) return false;
    if (f.colleges.length && !f.colleges.includes(collegeOf(c.unit_code))) return false;
    if (f.classes.length && !(c.classes ?? []).some((k) => f.classes.includes(k.code))) return false;
    if (f.categories.length && !f.categories.includes(c.requirement?.category ?? "unknown")) return false;
    if (f.emi === "emi" && !isEmi(c.language)) return false;
    if (f.emi === "non_emi" && isEmi(c.language)) return false; // 排除英文授課；未標語言者保留
    if (f.mprogram !== "all" && mprogramOids) {
      const inProgram = mprogramOids.has(c.offering_id);
      if (f.mprogram === "only" && !inProgram) return false;
      if (f.mprogram === "exclude" && inProgram) return false;
    }
    return true;
  });
}
