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
    expect(screen.getByText("資料結構")).toBeInTheDocument();
    expect(screen.getByText(/Data Structures/)).toBeInTheDocument();
    expect(screen.getByText(/2B05003/)).toBeInTheDocument();
    expect(screen.getByText(/王老師/)).toBeInTheDocument();
    expect(screen.getByText(/資工五/)).toBeInTheDocument();
    expect(screen.getByText(/限資工系/)).toBeInTheDocument();
  });
});
