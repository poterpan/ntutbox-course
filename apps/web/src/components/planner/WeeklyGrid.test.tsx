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

// Catalog always carries weekend courses (S=週六, U=週日) so we can prove the
// columns are driven by the draft `placed`, not by what the catalog contains.
const CATALOG = [
  { offering_id: "A", name: { zh: "微積分" }, meetings: [{ day: 1, periods: ["1"] }], teachers: [{ name: "王" }], classes: [], credits: 3 },
  { offering_id: "S", name: { zh: "週末班" }, meetings: [{ day: 6, periods: ["1"] }], teachers: [], classes: [], credits: 3 },
  { offering_id: "U", name: { zh: "週日班" }, meetings: [{ day: 0, periods: ["1"] }], teachers: [], classes: [], credits: 3 },
];

describe("WeeklyGrid weekend columns (data-driven by draft)", () => {
  beforeEach(() => {
    useTermStore.setState({ status: "ready", termKey: "115-1", error: null, generation: 1,
      bundle: bundleWith(CATALOG) });
  });

  it("placed only on weekdays → 週六/週日 hidden even though the catalog has weekend courses", () => {
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [{ offering_id: "A", priority: 1 }] });
    render(<WeeklyGrid />);
    ["週一", "週二", "週三", "週四", "週五"].forEach((d) => expect(screen.getByText(d)).toBeInTheDocument());
    expect(screen.queryByText("週六")).not.toBeInTheDocument();
    expect(screen.queryByText("週日")).not.toBeInTheDocument();
  });

  it("placing a 週六 course → 週六 column appears (週日 still hidden)", () => {
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [{ offering_id: "S", priority: 1 }] });
    render(<WeeklyGrid />);
    expect(screen.getByText("週六")).toBeInTheDocument();
    expect(screen.queryByText("週日")).not.toBeInTheDocument();
  });

  it("週日 sorts last when both 週六 and 週日 courses are placed", () => {
    useDraftStore.setState({ termKey: "115-1", favorites: [],
      placed: [{ offering_id: "U", priority: 1 }, { offering_id: "S", priority: 2 }] });
    render(<WeeklyGrid />);
    const labels = screen.getAllByText(/^週[一二三四五六日]$/).map((el) => el.textContent);
    expect(labels).toEqual(["週一", "週二", "週三", "週四", "週五", "週六", "週日"]);
  });

  it("renders a placed single course in its slot", () => {
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [{ offering_id: "A", priority: 1 }] });
    render(<WeeklyGrid />);
    expect(screen.getByText("微積分")).toBeInTheDocument();
  });
});
