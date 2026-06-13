import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SlotPopover } from "./SlotPopover";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";

const courses = [
  { offering_id: "A", name: { zh: "資料結構" }, credits: 3, teachers: [], meetings: [{ day: 3, periods: ["5"] }], classes: [] },
  { offering_id: "B", name: { zh: "演算法" }, credits: 3, teachers: [], meetings: [{ day: 3, periods: ["5"] }], classes: [] },
  { offering_id: "C", name: { zh: "機率論" }, credits: 3, teachers: [], meetings: [{ day: 3, periods: ["5"] }], classes: [] },
];

beforeEach(() => {
  useTermStore.setState({ status: "ready", termKey: "115-1", error: null, generation: 1,
    bundle: { termKey: "115-1", catalog: { courses } as never, periods: { periods: [] } as never, classes: { classes: [] } as never, enrollment: null } as never });
  useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [{ offering_id: "A", priority: 1 }, { offering_id: "B", priority: 2 }] });
  useUiStore.setState({ activeSlot: { day: 3, period: "5" } });
});

describe("SlotPopover", () => {
  it("lists placed-in-slot ordered by priority and addable others", () => {
    render(<SlotPopover />);
    expect(screen.getByText("資料結構")).toBeInTheDocument();
    expect(screen.getByText("演算法")).toBeInTheDocument();
    expect(screen.getByText("機率論")).toBeInTheDocument(); // addable (not placed)
  });
  it("move-up button raises priority (swaps B above A)", async () => {
    render(<SlotPopover />);
    await userEvent.click(screen.getByLabelText("演算法 上移"));
    const p = useDraftStore.getState().placed;
    const A = p.find((x) => x.offering_id === "A")!.priority;
    const B = p.find((x) => x.offering_id === "B")!.priority;
    expect(B).toBeLessThan(A);
  });
});
