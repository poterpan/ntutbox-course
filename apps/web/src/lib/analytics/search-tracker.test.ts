import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { reportSearchState, resetSearchTracker } from "./search-tracker";
import { resetAnalyticsState } from ".";
import { CONSENT_COOKIE, CONSENT_GRANTED } from "./consent";

let gtag: ReturnType<typeof vi.fn>;

const base = { termKey: "115-1", hasQuery: true, filterCount: 0, resultCount: 5 };

function searchEvents() {
  return gtag.mock.calls.filter((c) => c[0] === "event" && c[1] === "course_search");
}

beforeEach(() => {
  vi.useFakeTimers();
  resetAnalyticsState();
  resetSearchTracker();
  vi.stubEnv("NEXT_PUBLIC_GA_MEASUREMENT_ID", "G-TEST123");
  vi.stubEnv("NEXT_PUBLIC_GA_ENABLED", "true");
  vi.stubEnv("NEXT_PUBLIC_GA_DEBUG", "true");
  document.cookie = `${CONSENT_COOKIE}=${CONSENT_GRANTED}; Path=/`;
  gtag = vi.fn();
  window.gtag = gtag as unknown as typeof window.gtag;
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  document.cookie = `${CONSENT_COOKIE}=; Path=/; Max-Age=0`;
  delete window.gtag;
});

describe("course_search", () => {
  it("waits 500ms and sends only bucketed, query-free params", () => {
    reportSearchState({ ...base, resultCount: 42, filterCount: 2 });
    vi.advanceTimersByTime(499);
    expect(searchEvents()).toHaveLength(0);

    vi.advanceTimersByTime(1);
    expect(searchEvents()[0][2]).toEqual({
      site_surface: "course",
      term_key: "115-1",
      result_bucket: "11_50",
      filter_count_bucket: "2_plus",
    });
  });

  it("keeps restarting the debounce while the user is still typing", () => {
    reportSearchState({ ...base, resultCount: 100 });
    vi.advanceTimersByTime(400);
    reportSearchState({ ...base, resultCount: 30 });
    vi.advanceTimersByTime(400);
    reportSearchState({ ...base, resultCount: 4 });
    vi.advanceTimersByTime(400);
    expect(searchEvents()).toHaveLength(0);

    vi.advanceTimersByTime(100);
    expect(searchEvents()).toHaveLength(1);
    expect((searchEvents()[0][2] as Record<string, unknown>).result_bucket).toBe("1_10");
  });

  it("dedupes an identical normalized state", () => {
    reportSearchState({ ...base, resultCount: 3 });
    vi.advanceTimersByTime(500);
    // 不同字串、同一組 bucket → 不重送。
    reportSearchState({ ...base, resultCount: 7 });
    vi.advanceTimersByTime(500);
    expect(searchEvents()).toHaveLength(1);

    reportSearchState({ ...base, resultCount: 80 });
    vi.advanceTimersByTime(500);
    expect(searchEvents()).toHaveLength(2);
  });

  it("sends nothing when there is neither a query nor a filter", () => {
    reportSearchState({ ...base, hasQuery: false, filterCount: 0 });
    vi.advanceTimersByTime(500);
    expect(searchEvents()).toHaveLength(0);
  });

  it("counts a filter-only browse as a search", () => {
    reportSearchState({ ...base, hasQuery: false, filterCount: 1, resultCount: 0 });
    vi.advanceTimersByTime(500);
    expect(searchEvents()[0][2]).toEqual({
      site_surface: "course",
      term_key: "115-1",
      result_bucket: "0",
      filter_count_bucket: "1",
    });
  });

  it("re-arms after the user clears everything", () => {
    reportSearchState({ ...base, resultCount: 3 });
    vi.advanceTimersByTime(500);
    reportSearchState({ ...base, hasQuery: false, filterCount: 0 });
    vi.advanceTimersByTime(500);
    reportSearchState({ ...base, resultCount: 3 });
    vi.advanceTimersByTime(500);
    expect(searchEvents()).toHaveLength(2);
  });

  it("never puts the raw query anywhere in the payload", () => {
    reportSearchState({ ...base, resultCount: 3 });
    vi.advanceTimersByTime(500);
    expect(JSON.stringify(gtag.mock.calls)).not.toContain("微積分");
    const params = searchEvents()[0][2] as Record<string, unknown>;
    expect(Object.keys(params).sort()).toEqual([
      "filter_count_bucket",
      "result_bucket",
      "site_surface",
      "term_key",
    ]);
  });
});
