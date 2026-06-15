import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CourseListItem } from "./CourseListItem";
import type { CourseOffering } from "@/lib/data/types";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";
import { useIdentityStore } from "@/store/identity-store";

const course = {
  offering_id: "A", name: { zh: "微積分" }, credits: 3,
  teachers: [{ name: "王" }], meetings: [{ day: 1, periods: ["1"] }], classes: [],
} as unknown as CourseOffering;

beforeEach(() => {
  useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] });
  useUiStore.setState({ hoveredOfferingId: null });
  useIdentityStore.setState({ matricGroup: null });
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

describe("CourseListItem 學制徽章（學制感知）", () => {
  const withMatric = (code: string) => ({ ...course, raw_fields: { matric_codes: code } } as unknown as CourseOffering);

  it("未選學制 → 每組都標（含日間部大學部 matric 7）", () => {
    render(<CourseListItem course={withMatric("7")} />);
    expect(screen.getByText("日間部")).toBeInTheDocument();
  });

  it("未選學制 → 在職(A) 標『在職』、碩士(8) 標『研究所』", () => {
    const { unmount } = render(<CourseListItem course={withMatric("A")} />);
    expect(screen.getByText("在職")).toBeInTheDocument();
    unmount();
    render(<CourseListItem course={withMatric("8")} />);
    expect(screen.getByText("研究所")).toBeInTheDocument();
  });

  it("選了研究所 → 本學制(碩士 8) 不標，大學部(7) 反而被標", () => {
    useIdentityStore.setState({ matricGroup: "grad_day" });
    const { unmount } = render(<CourseListItem course={withMatric("8")} />);
    expect(screen.queryByText("研究所")).not.toBeInTheDocument();
    unmount();
    render(<CourseListItem course={withMatric("7")} />);
    expect(screen.getByText("日間部")).toBeInTheDocument();
  });
});
