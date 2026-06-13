import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// Mock the datasource module so page loads a tiny fake term.
vi.mock("@/lib/data", () => ({
  getDataSource: () => ({
    getManifest: vi.fn(),
    getTerm: vi.fn().mockResolvedValue({
      termKey: "115-1",
      catalog: { schema_version: 1, term: { key: "115-1", year: 115, semester: 1, label: "" },
        generated_at: null, source: {}, freshness: { catalog_crawled_at: "2026-06-13T05:00:00+08:00", enrollment_observed_at: null },
        courses: [{ offering_id: "1" }, { offering_id: "2" }] },
      periods: { schema_version: 1, timezone: "Asia/Taipei", periods: [] },
      classes: { schema_version: 1, term_key: "115-1", classes: [] },
      enrollment: { schema_version: 1, term_key: "115-1", observed_at: "2026-06-13T05:46:00+08:00", counts: {} },
    }),
  }),
}));

import Page from "./page";

describe("smoke page", () => {
  beforeEach(() => vi.restoreAllMocks());
  it("loads 115-1 and shows course count + catalog timestamp", async () => {
    render(<Page />);
    await waitFor(() => expect(screen.getByText(/2\s*門課/)).toBeInTheDocument());
    expect(screen.getByText(/115-1/)).toBeInTheDocument();
    expect(screen.getAllByText(/2026-06-13/).length).toBeGreaterThan(0);
  });
});
