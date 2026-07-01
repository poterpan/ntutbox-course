import { describe, expect, it } from "vitest";
import { buildCourseLink, parseCourseLink } from "./course-link";

describe("course-link", () => {
  it("build → parse round-trips", () => {
    const url = buildCourseLink({ termKey: "115-1", offeringId: "360744", origin: "https://x.test" });
    expect(url).toBe("https://x.test/?term=115-1&course=360744");
    const search = new URL(url).search;
    expect(parseCourseLink(search)).toEqual({ termKey: "115-1", offeringId: "360744" });
  });

  it("keeps term_key containing dashes intact", () => {
    const url = buildCourseLink({ termKey: "114-2", offeringId: "12345", origin: "https://x.test" });
    expect(parseCourseLink(new URL(url).search)).toEqual({ termKey: "114-2", offeringId: "12345" });
  });

  it("accepts a raw query string with or without leading ?", () => {
    expect(parseCourseLink("?term=115-1&course=1")).toEqual({ termKey: "115-1", offeringId: "1" });
    expect(parseCourseLink("term=115-1&course=1")).toEqual({ termKey: "115-1", offeringId: "1" });
  });

  it("returns null when either param is missing or blank", () => {
    expect(parseCourseLink("?term=115-1")).toBeNull();
    expect(parseCourseLink("?course=360744")).toBeNull();
    expect(parseCourseLink("?term=&course=360744")).toBeNull();
    expect(parseCourseLink("")).toBeNull();
  });
});
