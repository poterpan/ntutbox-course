import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CourseListItem } from "./CourseListItem";
import type { CourseOffering } from "@/lib/data/types";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";
import { useIdentityStore } from "@/store/identity-store";
import { EMPTY_FILTER } from "@/lib/filters/types";

const course = {
  offering_id: "A", name: { zh: "微積分" }, credits: 3,
  teachers: [{ name: "王" }], meetings: [{ day: 1, periods: ["1"] }], classes: [],
} as unknown as CourseOffering;

beforeEach(() => {
  useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] });
  useUiStore.setState({ hoveredOfferingId: null, filters: EMPTY_FILTER });
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

describe("CourseListItem 微學程 badge", () => {
  it("屬任一微學程 → 顯示單字「微」，全稱在 title/aria", () => {
    render(<CourseListItem course={course} mprogramOids={new Set(["A"])} />);
    const badge = screen.getByTitle("微學程");
    expect(badge).toHaveTextContent("微");
    expect(badge).toHaveAttribute("aria-label", "微學程");
  });
  it("不屬微學程 → 不顯示", () => {
    render(<CourseListItem course={course} mprogramOids={new Set(["Z"])} />);
    expect(screen.queryByTitle("微學程")).not.toBeInTheDocument();
  });
  it("未提供集合（資料未達）→ 不顯示", () => {
    render(<CourseListItem course={course} />);
    expect(screen.queryByTitle("微學程")).not.toBeInTheDocument();
  });
  it("filter=only（只看微學程）→ 隱藏「微」badge（整列皆微學程、零資訊）", () => {
    useUiStore.setState({ filters: { ...EMPTY_FILTER, mprogram: "only" } });
    render(<CourseListItem course={course} mprogramOids={new Set(["A"])} />);
    expect(screen.queryByTitle("微學程")).not.toBeInTheDocument();
  });
});

describe("CourseListItem 無時段圖示", () => {
  const noTimeCourse = { ...course, meetings: [] } as unknown as CourseOffering;
  it("無 meetings → 顯示時鐘斜線 icon（role=img + aria-label 全稱）", () => {
    render(<CourseListItem course={noTimeCourse} />);
    expect(screen.getByRole("img", { name: "無時段" })).toBeInTheDocument();
    expect(screen.getByLabelText("無時段")).toHaveAttribute("title", "無時段");
  });
  it("有 meetings → 不顯示", () => {
    render(<CourseListItem course={course} />);
    expect(screen.queryByLabelText("無時段")).not.toBeInTheDocument();
  });
});

describe("CourseListItem 學制徽章（學制感知）", () => {
  const withMatric = (code: string) => ({ ...course, raw_fields: { matric_codes: code } } as unknown as CourseOffering);

  it("未選學制 → 每組都標（單字「日」、全稱在 title；含日間部大學部 matric 7）", () => {
    render(<CourseListItem course={withMatric("7")} />);
    const badge = screen.getByTitle("日間部");
    expect(badge).toHaveTextContent("日");
    expect(badge).toHaveAttribute("aria-label", "日間部");
  });

  it("未選學制 → 在職(A) 標「職」、碩士(8) 標「研」", () => {
    const { unmount } = render(<CourseListItem course={withMatric("A")} />);
    expect(screen.getByTitle("在職")).toHaveTextContent("職");
    unmount();
    render(<CourseListItem course={withMatric("8")} />);
    expect(screen.getByTitle("研究所")).toHaveTextContent("研");
  });

  it("選了研究所 → 本學制(碩士 8) 不標，大學部(7) 反而被標", () => {
    useIdentityStore.setState({ matricGroup: "grad_day" });
    const { unmount } = render(<CourseListItem course={withMatric("8")} />);
    expect(screen.queryByTitle("研究所")).not.toBeInTheDocument();
    unmount();
    render(<CourseListItem course={withMatric("7")} />);
    expect(screen.getByTitle("日間部")).toBeInTheDocument();
  });
});
