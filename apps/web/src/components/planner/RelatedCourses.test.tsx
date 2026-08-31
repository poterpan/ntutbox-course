import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RelatedCourses } from "./RelatedCourses";
import { useTermStore } from "@/store/term-store";
import type { CourseOffering, TermBundle } from "@/lib/data/types";

// 測試 fixture 用寬鬆型別：只固定 offering_id，其餘欄位照各案例需要塞
// （CourseOffering 的巢狀 union 如 MatricSystem 會讓字面量推導失敗）。
function course(p: Record<string, unknown> & { offering_id: string }): CourseOffering {
  return {
    term_key: "115-1",
    name: { zh: `課-${p.offering_id}` },
    selection: { cwish_subj: p.offering_id },
    ...p,
  } as unknown as CourseOffering;
}

const SELF = course({ offering_id: "100", course_code: "X1", unit_code: "36", unit_name: "電子系" });
const SIBLING = course({
  offering_id: "101",
  course_code: "X1",
  unit_code: "36",
  unit_name: "電子系",
  classes: [{ code: "2891", name: "電子四甲" }],
});

function loadTerm(courses: CourseOffering[]) {
  useTermStore.setState({
    status: "ready",
    termKey: "115-1",
    bundle: { termKey: "115-1", catalog: { courses } } as unknown as TermBundle,
  });
}

beforeEach(() => {
  useTermStore.setState({ status: "idle", termKey: null, bundle: null });
  window.history.replaceState({}, "", "/?term=115-1&course=100");
});

describe("RelatedCourses", () => {
  it("renders real anchors to the course URL (not buttons — buttons give crawlers no path)", () => {
    loadTerm([SELF, SIBLING]);
    render(<RelatedCourses course={SELF} termKey="115-1" onSelect={() => {}} />);
    const link = screen.getByRole("link", { name: /課-101/ });
    expect(link).toHaveAttribute("href", "/?term=115-1&course=101");
  });

  it("shows the group heading and its stated criterion", () => {
    loadTerm([SELF, SIBLING]);
    render(<RelatedCourses course={SELF} termKey="115-1" onSelect={() => {}} />);
    expect(screen.getByText("同課其他班")).toBeInTheDocument();
    expect(screen.getByText(/課程編碼 X1/)).toBeInTheDocument();
  });

  it("renders nothing when the course has no related offering", () => {
    loadTerm([SELF]);
    const { container } = render(<RelatedCourses course={SELF} termKey="115-1" onSelect={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("intercepts a plain click: swaps in place and pushes the new URL", async () => {
    loadTerm([SELF, SIBLING]);
    const onSelect = vi.fn();
    render(<RelatedCourses course={SELF} termKey="115-1" onSelect={onSelect} />);
    await userEvent.click(screen.getByRole("link", { name: /課-101/ }));
    expect(onSelect).toHaveBeenCalledWith("101");
    expect(window.location.search).toBe("?term=115-1&course=101");
  });

  it("leaves the URL alone when syncUrl is off (shared-plan modal owns the address)", async () => {
    loadTerm([SELF, SIBLING]);
    const onSelect = vi.fn();
    render(<RelatedCourses course={SELF} termKey="115-1" onSelect={onSelect} syncUrl={false} />);
    await userEvent.click(screen.getByRole("link", { name: /課-101/ }));
    expect(onSelect).toHaveBeenCalledWith("101");
    expect(window.location.search).toBe("?term=115-1&course=100");
  });

  it("does not intercept a modifier-click, so 'open in new tab' still works", () => {
    // userEvent 不轉發 event-init，修飾鍵要用 fireEvent 直接帶。
    loadTerm([SELF, SIBLING]);
    const onSelect = vi.fn();
    render(<RelatedCourses course={SELF} termKey="115-1" onSelect={onSelect} />);
    for (const mod of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) {
      fireEvent.click(screen.getByRole("link", { name: /課-101/ }), mod);
    }
    expect(onSelect).not.toHaveBeenCalled();
    expect(window.location.search).toBe("?term=115-1&course=100");
  });
});
