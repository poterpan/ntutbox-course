import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";

vi.mock("@/lib/data", () => ({
  getDataSource: () => ({
    getManifest: vi.fn().mockResolvedValue({ schema_version: 2, terms: { "115-1": {} } }),
    getTerm: vi.fn().mockResolvedValue({
      termKey: "115-1",
      catalog: { courses: [{ offering_id: "A", name: { zh: "微積分" }, credits: 3, teachers: [{ name: "王" }], meetings: [{ day: 1, periods: ["1"] }], classes: [], unit_code: "59", unit_name: "資工" }],
        term: { key: "115-1" }, freshness: { catalog_crawled_at: "2026-06-13T05:00:00+08:00" } },
      periods: { periods: [{ token: "1", order: 0, start_hm: "08:10", end_hm: "09:00", label: "1" }] },
      classes: { classes: [] }, enrollment: { observed_at: "2026-06-13T05:46:00+08:00", counts: {} },
    }),
  }),
}));

vi.mock("@/lib/planner/use-mprograms", () => ({ useMprograms: vi.fn() }));

import { PlannerLayout } from "./PlannerLayout";
import { useUiStore } from "@/store/ui-store";
import { useMprograms } from "@/lib/planner/use-mprograms";

const mockedMprograms = vi.mocked(useMprograms);
const mprogramDir = {
  schema_version: 2,
  term_key: "115-1",
  programs: [{ code: "AV2", name: "面板微學程", offering_ids: ["1", "2"], courses: [], rules_text: null }],
} as never;

// jsdom 無 matchMedia；模擬視窗寬度（matches=true 代表 < lg）。
function mockMatchMedia(matches: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches, media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  })) as never;
}

beforeEach(() => {
  vi.restoreAllMocks();
  delete (window as { matchMedia?: unknown }).matchMedia;
  useUiStore.setState({ libraryTab: "courses", selectedProgramCode: null, libraryOpen: false });
  mockedMprograms.mockReturnValue({ data: mprogramDir, loading: false, error: false, retry: vi.fn() });
});

describe("PlannerLayout (integration)", () => {
  it("boots, shows grid + library + credit bar, course searchable", async () => {
    render(<PlannerLayout />);
    await waitFor(() => expect(screen.getByText("微積分")).toBeInTheDocument()); // in library list
    expect(screen.getByText("週一")).toBeInTheDocument(); // grid weekday header
    expect(screen.getAllByText(/第一志願/).length).toBeGreaterThan(0);  // credit bar
    expect(screen.getByLabelText("搜尋課程")).toBeInTheDocument();
  });

  it("點微學程 tab → 顯示微學程列表", async () => {
    render(<PlannerLayout />);
    await waitFor(() => expect(screen.getByText("微積分")).toBeInTheDocument()); // booted on 課程庫
    fireEvent.click(screen.getByRole("button", { name: "微學程" }));
    expect(screen.getByPlaceholderText("搜尋微學程…")).toBeInTheDocument();
    expect(screen.getByText("面板微學程")).toBeInTheDocument();
  });

  // 迴歸：openProgram 設 libraryOpen=true 供手機開 bottom-sheet；SheetContent portal 逃出 lg:hidden，
  // 桌機須以視窗寬度 gating，避免把 sheet 疊在常駐右欄上（重複呈現面板詳情）。
  it("桌機(≥lg)：libraryOpen=true 不開手機 sheet（無 dialog 疊層，面板留在常駐右欄）", async () => {
    mockMatchMedia(false);
    render(<PlannerLayout />);
    await waitFor(() => expect(screen.getByText("微積分")).toBeInTheDocument());
    await act(async () => {
      useUiStore.setState({ libraryTab: "programs", selectedProgramCode: "AV2", libraryOpen: true });
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("heading", { name: "面板微學程", level: 2 })).toBeInTheDocument();
  });

  it("手機(<lg)：libraryOpen=true 開 bottom-sheet dialog", async () => {
    mockMatchMedia(true);
    render(<PlannerLayout />);
    await waitFor(() => expect(screen.getByText("微積分")).toBeInTheDocument());
    await act(async () => {
      useUiStore.setState({ libraryTab: "programs", selectedProgramCode: "AV2", libraryOpen: true });
    });
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});
