import { describe, it, expect, beforeEach, vi } from "vitest";
import { useTermStore } from "./term-store";
import type { DataSource } from "@/lib/data";
import type { TermBundle, Manifest } from "@/lib/data/types";

function fakeBundle(termKey: string): TermBundle {
  return {
    termKey,
    catalog: { schema_version: 1, term: { key: termKey, year: 115, semester: 1, label: "" },
      generated_at: null, source: {} as never, freshness: { catalog_crawled_at: "2026-06-13T05:00:00+08:00", enrollment_observed_at: null }, courses: [] },
    periods: { schema_version: 1, timezone: "Asia/Taipei", periods: [] },
    classes: { schema_version: 1, term_key: termKey, classes: [] },
    enrollment: { schema_version: 1, term_key: termKey, observed_at: "2026-06-13T05:46:00+08:00", counts: {} },
  };
}

describe("term-store", () => {
  beforeEach(() => useTermStore.setState({ status: "idle", termKey: null, bundle: null, error: null, generation: 0 }));

  it("loadTerm moves idle→loading→ready and stores bundle", async () => {
    const ds: DataSource = {
      getManifest: vi.fn(),
      getTerm: vi.fn().mockResolvedValue(fakeBundle("115-1")),
    };
    await useTermStore.getState().loadTerm("115-1", ds);
    const s = useTermStore.getState();
    expect(s.status).toBe("ready");
    expect(s.termKey).toBe("115-1");
    expect(s.catalogCrawledAt()).toBe("2026-06-13T05:00:00+08:00");
    expect(s.enrollmentObservedAt()).toBe("2026-06-13T05:46:00+08:00");
  });

  it("discards a stale (superseded) load (generation token)", async () => {
    let resolveSlow!: (b: TermBundle) => void;
    const slow = new Promise<TermBundle>((r) => (resolveSlow = r));
    const ds: DataSource = {
      getManifest: vi.fn(),
      getTerm: vi.fn()
        .mockImplementationOnce(() => slow)              // first (114-2) is slow
        .mockResolvedValueOnce(fakeBundle("115-1")),     // second (115-1) is fast
    };
    const p1 = useTermStore.getState().loadTerm("114-2", ds);
    const p2 = useTermStore.getState().loadTerm("115-1", ds);
    await p2;                                            // 115-1 finishes first
    resolveSlow(fakeBundle("114-2"));                    // stale 114-2 resolves late
    await p1;
    expect(useTermStore.getState().termKey).toBe("115-1"); // stale result ignored
  });

  it("sets status=error on failure", async () => {
    const ds: DataSource = { getManifest: vi.fn(), getTerm: vi.fn().mockRejectedValue(new Error("boom")) };
    await useTermStore.getState().loadTerm("115-1", ds);
    expect(useTermStore.getState().status).toBe("error");
    expect(useTermStore.getState().error).toContain("boom");
  });
});
