import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// vitest 的 cwd = apps/web
const src = (rel: string) => readFileSync(resolve(process.cwd(), "src", rel), "utf8");

// 交接文檔 §9 的硬界線，靠測試守住而不只是靠 code review。
describe("analytics boundaries", () => {
  it("draft-store has no analytics side effects (要保持可測、可離線)", () => {
    const code = src("store/draft-store.ts");
    // 註解可以提到 analytics（說明為什麼 place() 要回傳 outcome），但**不得 import**。
    expect(code).not.toMatch(/from\s+["'][^"']*analytics/);
    expect(code).not.toContain("gtag");
  });

  it("business components never call window.gtag directly", () => {
    for (const file of [
      "components/planner/CourseListItem.tsx",
      "components/planner/CourseDetailContent.tsx",
      "components/planner/SlotPopover.tsx",
      "components/planner/SharedTimetableModal.tsx",
      "components/planner/CreditSummary.tsx",
      "components/planner/CourseLibrary.tsx",
    ]) {
      expect(src(file)).not.toContain("gtag");
    }
  });
});
