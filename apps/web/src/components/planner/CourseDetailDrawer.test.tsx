import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { CourseDetailDrawer } from "./CourseDetailDrawer";
import { useTermStore } from "@/store/term-store";
import { useUiStore } from "@/store/ui-store";

beforeEach(() => {
  useTermStore.setState({ status: "ready", termKey: "115-1", error: null, generation: 1,
    bundle: { termKey: "115-1", catalog: { courses: [
      { offering_id: "A", course_code: "2B05003", name: { zh: "資料結構", en: "Data Structures" }, credits: 3,
        teachers: [{ name: "王老師" }], meetings: [{ day: 1, periods: ["3", "4"] }], classes: [{ code: "2652", name: "資工五", kind: "regular" }],
        unit_name: "資工", language: "中文", notes_raw: "限資工系" },
    ] } as never, periods: { periods: [] } as never, classes: { classes: [] } as never, enrollment: null } as never });
  useUiStore.setState({ detailOfferingId: "A" });
});

describe("CourseDetailDrawer", () => {
  it("shows catalog fields for the selected course", () => {
    render(<CourseDetailDrawer />);
    // Name appears both as heading and as a Dcard chip; assert the heading specifically.
    expect(screen.getByRole("heading", { name: "資料結構" })).toBeInTheDocument();
    // English name intentionally NOT shown (zh-only until an English site exists)
    expect(screen.queryByText(/Data Structures/)).not.toBeInTheDocument();
    expect(screen.getByText(/2B05003/)).toBeInTheDocument();
    // Teacher name appears in the 授課教師 row and as a Dcard chip; target the row cell.
    expect(screen.getByText("王老師", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText(/資工五/)).toBeInTheDocument();
    expect(screen.getByText(/限資工系/)).toBeInTheDocument();
  });

  it("links course name and each teacher to a Dcard ntut-forum search", () => {
    render(<CourseDetailDrawer />);
    expect(screen.getByRole("link", { name: "在 Dcard 搜尋「資料結構」" })).toHaveAttribute(
      "href",
      `https://www.dcard.tw/search?query=${encodeURIComponent("資料結構")}&forum=ntut`,
    );
    expect(screen.getByRole("link", { name: "在 Dcard 搜尋「王老師」" })).toHaveAttribute(
      "href",
      `https://www.dcard.tw/search?query=${encodeURIComponent("王老師")}&forum=ntut`,
    );
  });
});
