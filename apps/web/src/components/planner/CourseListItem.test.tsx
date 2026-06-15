import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CourseListItem } from "./CourseListItem";
import type { CourseOffering } from "@/lib/data/types";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";

const course = {
  offering_id: "A", name: { zh: "微積分" }, credits: 3,
  teachers: [{ name: "王" }], meetings: [{ day: 1, periods: ["1"] }], classes: [],
} as unknown as CourseOffering;

beforeEach(() => {
  useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] });
  useUiStore.setState({ hoveredOfferingId: null });
});

describe("CourseListItem hover preview (desktop)", () => {
  it("mouse pointer enter sets hoveredOfferingId; leave clears it", () => {
    render(<CourseListItem course={course} />);
    const row = screen.getByText("微積分").closest("[data-offering-id]")!;
    fireEvent.pointerEnter(row, { pointerType: "mouse" });
    expect(useUiStore.getState().hoveredOfferingId).toBe("A");
    fireEvent.pointerLeave(row, { pointerType: "mouse" });
    expect(useUiStore.getState().hoveredOfferingId).toBe(null);
  });

  it("touch pointer enter does NOT set hoveredOfferingId", () => {
    render(<CourseListItem course={course} />);
    const row = screen.getByText("微積分").closest("[data-offering-id]")!;
    fireEvent.pointerEnter(row, { pointerType: "touch" });
    expect(useUiStore.getState().hoveredOfferingId).toBe(null);
  });

  it("placing a course clears any lingering hover (no stale ghost)", async () => {
    render(<CourseListItem course={course} />);
    const row = screen.getByText("微積分").closest("[data-offering-id]")!;
    fireEvent.pointerEnter(row, { pointerType: "mouse" });
    expect(useUiStore.getState().hoveredOfferingId).toBe("A");
    await userEvent.click(screen.getByLabelText("排入"));
    expect(useDraftStore.getState().placed.map((p) => p.offering_id)).toEqual(["A"]);
    expect(useUiStore.getState().hoveredOfferingId).toBe(null);
  });
});
