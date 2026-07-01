import { describe, expect, it } from "vitest";
import { buildPlanLink, parsePlanLink } from "./plan-link";

describe("plan-link", () => {
  it("build → parse round-trips with order preserved (order = priority)", () => {
    const url = buildPlanLink({
      termKey: "115-1",
      offeringIds: ["360744", "360745", "360763"],
      origin: "https://x.test",
    });
    expect(url).toBe("https://x.test/?term=115-1&plan=360744.360745.360763");
    expect(parsePlanLink(new URL(url).search)).toEqual({
      termKey: "115-1",
      offeringIds: ["360744", "360745", "360763"],
    });
  });

  it("keeps term_key dashes; accepts raw query with/without leading ?", () => {
    expect(parsePlanLink("?term=114-2&plan=1.2")).toEqual({ termKey: "114-2", offeringIds: ["1", "2"] });
    expect(parsePlanLink("term=114-2&plan=1.2")).toEqual({ termKey: "114-2", offeringIds: ["1", "2"] });
  });

  it("returns null when a param is missing or the plan is empty", () => {
    expect(parsePlanLink("?term=115-1")).toBeNull();
    expect(parsePlanLink("?plan=1.2")).toBeNull();
    expect(parsePlanLink("?term=115-1&plan=")).toBeNull();
    expect(parsePlanLink("")).toBeNull();
  });
});
