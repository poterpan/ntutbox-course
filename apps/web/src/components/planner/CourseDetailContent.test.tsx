import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CourseDetailContent } from "./CourseDetailContent";
import { useTermStore } from "@/store/term-store";
import { useUiStore } from "@/store/ui-store";

// 只驗證「所屬微學程 chips」這層 enrichment；microprogram 目錄以 mock 注入，
// 不打真 fetch。buildProgramIndex 走真實實作（offering→programs 反查）。
const { mockUseMprograms } = vi.hoisted(() => ({ mockUseMprograms: vi.fn() }));
vi.mock("@/lib/planner/use-mprograms", () => ({ useMprograms: mockUseMprograms }));

const dirWith = { schema_version: 2, term_key: "115-1", programs: [
  { code: "AV2", name: "面板微學程", offering_ids: ["A"], courses: [], rules_text: null },
] } as never;
const dirNone = { schema_version: 2, term_key: "115-1", programs: [
  { code: "AV3", name: "創業家精神微學程", offering_ids: ["Z"], courses: [], rules_text: null },
] } as never;

function seedTerm() {
  useTermStore.setState({ status: "ready", termKey: "115-1", error: null, generation: 1,
    bundle: { termKey: "115-1", catalog: { courses: [
      { offering_id: "A", course_code: "2B05003", name: { zh: "資料結構", en: "Data Structures" }, credits: 3,
        teachers: [{ name: "王老師" }], meetings: [{ day: 1, periods: ["3", "4"] }], classes: [{ code: "2652", name: "資工五", kind: "regular" }],
        unit_name: "資工", language: "中文", notes_raw: "限資工系" },
    ] } as never, periods: { periods: [] } as never, classes: { classes: [] } as never, enrollment: null } as never });
}

beforeEach(() => {
  seedTerm();
  useUiStore.setState({ libraryTab: "courses", selectedProgramCode: null, detailOfferingId: "A", libraryOpen: false });
  mockUseMprograms.mockReset();
});

describe("CourseDetailContent — 所屬微學程 chips", () => {
  it("renders a chip for each owning micro-program and jumps on click", () => {
    mockUseMprograms.mockReturnValue({ data: dirWith, error: false, loading: false, retry: vi.fn() });
    render(<CourseDetailContent offeringId="A" />);

    const chip = screen.getByRole("button", { name: /面板微學程/ });
    expect(chip).toBeInTheDocument();

    fireEvent.click(chip);
    const s = useUiStore.getState();
    expect(s.libraryTab).toBe("programs");
    expect(s.selectedProgramCode).toBe("AV2");
    expect(s.detailOfferingId).toBeNull();
  });

  it("renders nothing when the course belongs to no micro-program", () => {
    mockUseMprograms.mockReturnValue({ data: dirNone, error: false, loading: false, retry: vi.fn() });
    render(<CourseDetailContent offeringId="A" />);
    expect(screen.queryByRole("button", { name: /微學程/ })).not.toBeInTheDocument();
    expect(screen.queryByText("所屬微學程")).not.toBeInTheDocument();
  });

  it("hides the block when showProgramChips=false, even with owning programs (shared-modal 就地詳情)", () => {
    mockUseMprograms.mockReturnValue({ data: dirWith, error: false, loading: false, retry: vi.fn() });
    render(<CourseDetailContent offeringId="A" showProgramChips={false} />);
    expect(screen.queryByRole("button", { name: /面板微學程/ })).not.toBeInTheDocument();
    expect(screen.queryByText("所屬微學程")).not.toBeInTheDocument();
  });

  it("stays silent when the directory failed / is not yet loaded", () => {
    mockUseMprograms.mockReturnValue({ data: null, error: true, loading: false, retry: vi.fn() });
    render(<CourseDetailContent offeringId="A" />);
    expect(screen.queryByText("所屬微學程")).not.toBeInTheDocument();
  });
});
