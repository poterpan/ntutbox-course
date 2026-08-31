/**
 * 用 repo 內已 commit 的真實 catalog fixture 驗「沒有孤島」這個核心不變量。
 *
 * 這條是本次改動的整個重點：SEO 稽核發現 sitemap 裡每個課程頁的內部連結數是 0。
 * 上面那些單元測試驗的是函式行為；這支驗的是**對真資料仍然成立**——
 * 每一門非佔位課都至少被某個系所 hub 連到，而且每一門課都連得出去。
 * 資料改版（新學期、新單位代碼）若破壞這個性質，這支會先炸，不會等到上線。
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { CourseOffering, TermCatalog } from "@/lib/data/types";
import { buildUnitHubs, unitSlug } from "./units";
import { buildRelated } from "./related";

const FIXTURE = path.join(process.cwd(), "public", "data", "v1", "terms", "115-1", "catalog.json");
const courses: CourseOffering[] = (JSON.parse(readFileSync(FIXTURE, "utf8")) as TermCatalog).courses ?? [];

describe("hub coverage over the real 115-1 catalog", () => {
  it("has a non-trivial fixture to reason about", () => {
    expect(courses.length).toBeGreaterThan(2000);
  });

  it("links every non-placeholder course from exactly one unit hub", () => {
    const hubs = buildUnitHubs(courses);
    const linked = hubs.flatMap((h) => h.courses.map((c) => c.offeringId));
    const expected = courses.filter((c) => !c.is_placeholder).map((c) => c.offering_id);

    expect(new Set(linked).size).toBe(linked.length); // 無重複 → 每課恰好一個 hub
    expect(new Set(linked)).toEqual(new Set(expected));
    expect(linked.length).toBe(expected.length);
  });

  it("keeps every hub reachable at a stable /browse/<slug>/ path", () => {
    const hubs = buildUnitHubs(courses);
    expect(hubs.length).toBeGreaterThan(50);
    expect(new Set(hubs.map((h) => h.slug)).size).toBe(hubs.length);
    // 沒有撞名 → slug 可由 unit_code 直接推得，課程頁上的「開課單位」回連才不會 404。
    for (const h of hubs) expect(h.slug).toBe(unitSlug(h.unitCode));
    for (const h of hubs) expect(h.slug).toMatch(/^[0-9a-z][0-9a-z-]*$/);
  });

  it("gives every course at least one outbound cross-link (no dead end in the graph)", () => {
    const linkable = courses.filter((c) => !c.is_placeholder);
    const orphans = linkable.filter((c) => buildRelated(c, courses).length === 0);
    // 唯一可接受的例外：整個開課單位只有這一門課、且沒有兄弟班也沒有掛教師。
    for (const o of orphans) {
      const unitMates = linkable.filter((c) => c.unit_code === o.unit_code && c.offering_id !== o.offering_id);
      expect(unitMates).toHaveLength(0);
    }
    expect(orphans.length / linkable.length).toBeLessThan(0.01);
  });

  it("caps outbound cross-links so no course page turns into a link farm", () => {
    const worst = courses
      .filter((c) => !c.is_placeholder)
      .reduce((m, c) => Math.max(m, buildRelated(c, courses).reduce((n, g) => n + g.items.length, 0)), 0);
    expect(worst).toBeLessThanOrEqual(22);
  });
});
