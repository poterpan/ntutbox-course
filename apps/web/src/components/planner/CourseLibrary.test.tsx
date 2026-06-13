import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CourseLibrary } from "./CourseLibrary";
import { useTermStore } from "@/store/term-store";
import { useUiStore } from "@/store/ui-store";
import { EMPTY_FILTER } from "@/lib/filters/types";

const courses = [
  { offering_id: "A", name: { zh: "微積分" }, credits: 3, teachers: [{ name: "王" }], meetings: [{ day: 1, periods: ["1"] }], classes: [], unit_code: "59" },
  { offering_id: "B", name: { zh: "演算法" }, credits: 3, teachers: [{ name: "李" }], meetings: [{ day: 3, periods: ["5"] }], classes: [], unit_code: "59" },
];

/** 250 fake courses all in unit "59" — used to verify filter-only browse isn't capped pre-filter. */
const bigUnitCourses = Array.from({ length: 250 }, (_, i) => ({
  offering_id: `U${i}`,
  name: { zh: `課程${i}` },
  credits: 3,
  teachers: [],
  meetings: [],
  classes: [],
  unit_code: "59",
  unit_name: "大單位",
}));

beforeEach(() => {
  useUiStore.setState({ query: "", filters: EMPTY_FILTER });
  useTermStore.setState({ status: "ready", termKey: "115-1", error: null, generation: 1,
    bundle: { termKey: "115-1", catalog: { courses } as never, periods: { periods: [] } as never, classes: { classes: [] } as never, enrollment: null } as never });
});

describe("CourseLibrary", () => {
  it("filters results live by search query", async () => {
    render(<CourseLibrary />);
    expect(screen.getByText("微積分")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("搜尋課程"), "演算");
    await waitFor(() => {
      expect(screen.queryByText("微積分")).not.toBeInTheDocument();
      expect(screen.getByText("演算法")).toBeInTheDocument();
    });
  });

  it("filter-only browse with >200 matching courses shows true filtered total, not silently capped to 200", () => {
    // Set up 250 courses all in unit "59" and activate a unit filter with an empty search query.
    useTermStore.setState({
      status: "ready", termKey: "115-1", error: null, generation: 1,
      bundle: {
        termKey: "115-1",
        catalog: { courses: bigUnitCourses } as never,
        periods: { periods: [] } as never,
        classes: { classes: [] } as never,
        enrollment: null,
      } as never,
    });
    useUiStore.setState({ query: "", filters: { ...EMPTY_FILTER, units: ["59"] } });

    render(<CourseLibrary />);

    // The count text must reflect the true filtered total (250), not the display cap (200).
    expect(screen.getByText(/250 門課/)).toBeInTheDocument();
    // And the "已達上限" hint should be visible because 250 > 200.
    expect(screen.getByText(/已達上限/)).toBeInTheDocument();
  });
});
