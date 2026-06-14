import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { TimetableCell } from "./TimetableCell";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";

const courses = [
  { offering_id: "A", name: { zh: "資料結構" }, meetings: [{ day: 3, periods: ["5"] }], teachers: [], classes: [], credits: 3 },
  { offering_id: "B", name: { zh: "演算法" }, meetings: [{ day: 3, periods: ["5"] }], teachers: [], classes: [], credits: 3 },
  { offering_id: "C", name: { zh: "機率論" }, meetings: [{ day: 3, periods: ["5"] }], teachers: [], classes: [], credits: 3 },
];

beforeEach(() => {
  useDraftStore.setState({ termKey: "115-1", favorites: [],
    placed: [{ offering_id: "A", priority: 1 }, { offering_id: "B", priority: 2 }, { offering_id: "C", priority: 3 }] });
  useTermStore.setState({ status: "ready", termKey: "115-1", error: null, generation: 1,
    bundle: { termKey: "115-1", catalog: { courses } as never, periods: {} as never, classes: {} as never, enrollment: null } as never });
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
