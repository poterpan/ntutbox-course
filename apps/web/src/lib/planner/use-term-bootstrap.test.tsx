import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useTermBootstrap } from "./use-term-bootstrap";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";

vi.mock("@/lib/data", () => ({
  getDataSource: () => ({
    getManifest: vi.fn().mockResolvedValue({ schema_version: 1, terms: { "115-1": {}, "114-2": {} } }),
    getTerm: vi.fn().mockResolvedValue({
      termKey: "115-1", catalog: { courses: [{ offering_id: "A", name: { zh: "x" }, meetings: [], classes: [], teachers: [] }], term: { key: "115-1" }, freshness: {} },
      periods: { periods: [] }, classes: { classes: [] }, enrollment: null,
    }),
  }),
}));

beforeEach(() => {
  useDraftStore.setState({ termKey: "", favorites: [], placed: [{ offering_id: "GONE", priority: 1 }] });
  useTermStore.setState({ status: "idle", termKey: null, bundle: null, error: null, generation: 0 });
});

describe("useTermBootstrap", () => {
  it("loads default term then reconciles stale drafts (drops GONE)", async () => {
    renderHook(() => useTermBootstrap());
    await waitFor(() => expect(useTermStore.getState().status).toBe("ready"));
    await waitFor(() => expect(useDraftStore.getState().placed).toEqual([]));
  });
});
