import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { WeeklyGrid } from "./WeeklyGrid";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";
import type { TermBundle } from "@/lib/data/types";

function bundleWith(courses: unknown[]): TermBundle {
  return {
    termKey: "115-1",
    catalog: { schema_version: 1, term: { key: "115-1", year: 115, semester: 1, label: "" }, generated_at: null, source: {} as never, freshness: {}, courses } as never,
    periods: { schema_version: 1, timezone: "Asia/Taipei", periods: [
      { token: "1", order: 0, start_hm: "08:10", end_hm: "09:00", label: "1" },
      { token: "2", order: 1, start_hm: "09:10", end_hm: "10:00", label: "2" },
    ] } as never,
    classes: { schema_version: 1, term_key: "115-1", classes: [] } as never,
    enrollment: null,
  };
}

describe("WeeklyGrid", () => {
  beforeEach(() => {
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [{ offering_id: "A", priority: 1 }] });
    useTermStore.setState({ status: "ready", termKey: "115-1", error: null, generation: 1,
      bundle: bundleWith([{ offering_id: "A", name: { zh: "微積分" }, meetings: [{ day: 1, periods: ["1"] }], teachers: [{ name: "王" }], classes: [], credits: 3 }]) });
  });

  it("renders weekday headers 一..六 and period rows", () => {
    render(<WeeklyGrid />);
    ["一", "二", "三", "四", "五", "六"].forEach((d) => expect(screen.getByText(d)).toBeInTheDocument());
  });

  it("renders a placed single course in its slot", () => {
    render(<WeeklyGrid />);
    expect(screen.getByText("微積分")).toBeInTheDocument();
  });
});
