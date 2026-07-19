import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

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

beforeEach(() => {
  vi.restoreAllMocks();
  useUiStore.setState({ libraryTab: "courses", selectedProgramCode: null });
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
});
