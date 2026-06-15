import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { TimetableCell } from "./TimetableCell";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";

const courses = [
  { offering_id: "A", name: { zh: "資料結構" }, meetings: [{ day: 3, periods: ["5"] }], teachers: [], classes: [], credits: 3 },
  { offering_id: "B", name: { zh: "演算法" }, meetings: [{ day: 3, periods: ["5"] }], teachers: [], classes: [], credits: 3 },
  { offering_id: "C", name: { zh: "機率論" }, meetings: [{ day: 3, periods: ["5"] }], teachers: [], classes: [], credits: 3 },
  // hover-preview fixtures
  { offering_id: "H", name: { zh: "微積分" }, meetings: [{ day: 1, periods: ["2"] }], teachers: [], classes: [], credits: 3 },
  { offering_id: "NT", name: { zh: "無時段課" }, meetings: [], teachers: [], classes: [], credits: 3 },
];

beforeEach(() => {
  useDraftStore.setState({ termKey: "115-1", favorites: [],
    placed: [{ offering_id: "A", priority: 1 }, { offering_id: "B", priority: 2 }, { offering_id: "C", priority: 3 }] });
  useTermStore.setState({ status: "ready", termKey: "115-1", error: null, generation: 1,
    bundle: { termKey: "115-1", catalog: { courses } as never, periods: {} as never, classes: {} as never, enrollment: null } as never });
  useUiStore.setState({ hoveredOfferingId: null });
});

describe("conflict cell", () => {
  it("desktop: first preference prominent + later prefs as small names", () => {
    render(<TimetableCell day={3} period="5" />);
    expect(screen.getByText("資料結構")).toBeInTheDocument(); // first pref
    expect(screen.getByText("演算法")).toBeInTheDocument();   // small
    expect(screen.getByText("機率論")).toBeInTheDocument();
    expect(screen.getByTestId("conflict-cell")).toBeInTheDocument();
  });
});

describe("hover ghost preview", () => {
  it("draws a ghost on the cells the hovered course meets in", () => {
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] });
    useUiStore.setState({ hoveredOfferingId: "H" }); // H meets day1/period2
    render(<TimetableCell day={1} period="2" />);
    expect(screen.getByTestId("ghost-cell")).toBeInTheDocument();
  });

  it("no ghost on cells the hovered course does NOT meet in", () => {
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] });
    useUiStore.setState({ hoveredOfferingId: "H" });
    render(<TimetableCell day={4} period="5" />);
    expect(screen.queryByTestId("ghost-cell")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ghost-conflict-cell")).not.toBeInTheDocument();
  });

  it("ghost turns red (衝堂) when the cell is already occupied by a placed course", () => {
    // A is placed at day3/period5; hovering H-but-pretend overlap: use a hovered
    // course that also meets day3/period5 to overlap the placed A.
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [{ offering_id: "A", priority: 1 }] });
    useUiStore.setState({ hoveredOfferingId: "B" }); // B meets day3/period5, A already there
    render(<TimetableCell day={3} period="5" />);
    expect(screen.getByTestId("ghost-conflict-cell")).toBeInTheDocument();
    expect(screen.queryByTestId("ghost-cell")).not.toBeInTheDocument();
  });

  it("no ghost when nothing is hovered", () => {
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] });
    render(<TimetableCell day={1} period="2" />);
    expect(screen.queryByTestId("ghost-cell")).not.toBeInTheDocument();
  });

  it("a course with no meetings draws no ghost anywhere", () => {
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] });
    useUiStore.setState({ hoveredOfferingId: "NT" }); // no meetings
    render(<TimetableCell day={1} period="2" />);
    expect(screen.queryByTestId("ghost-cell")).not.toBeInTheDocument();
  });
});
