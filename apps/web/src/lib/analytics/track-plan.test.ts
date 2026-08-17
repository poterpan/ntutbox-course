import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { placeTracked, trackPlanCreatedTransition } from "./track-plan";
import { resetAnalyticsState } from ".";
import { CONSENT_COOKIE, CONSENT_GRANTED } from "./consent";
import { resetSessionFallback } from "./storage";
import { useDraftStore } from "@/store/draft-store";
import { useTermStore } from "@/store/term-store";

let gtag: ReturnType<typeof vi.fn>;

function eventsNamed(name: string) {
  return gtag.mock.calls.filter((c) => c[0] === "event" && c[1] === name);
}

beforeEach(() => {
  resetAnalyticsState();
  resetSessionFallback();
  window.sessionStorage.clear();
  vi.stubEnv("NEXT_PUBLIC_GA_MEASUREMENT_ID", "G-TEST123");
  vi.stubEnv("NEXT_PUBLIC_GA_ENABLED", "true");
  vi.stubEnv("NEXT_PUBLIC_GA_DEBUG", "true");
  document.cookie = `${CONSENT_COOKIE}=${CONSENT_GRANTED}; Path=/`;
  gtag = vi.fn();
  window.gtag = gtag as unknown as typeof window.gtag;
  useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] });
  useTermStore.setState({ status: "ready", termKey: "115-1", bundle: null, error: null, generation: 1 });
});

afterEach(() => {
  vi.unstubAllEnvs();
  document.cookie = `${CONSENT_COOKIE}=; Path=/; Max-Age=0`;
  delete window.gtag;
});

describe("placeTracked", () => {
  it("places the course and sends course_added with the caller's placement", () => {
    placeTracked("360744", "course_list");
    expect(useDraftStore.getState().placed.map((p) => p.offering_id)).toEqual(["360744"]);
    expect(eventsNamed("course_added")[0][2]).toEqual({
      site_surface: "course",
      term_key: "115-1",
      placement: "course_list",
      placed_count_bucket: "1",
    });
  });

  it("sends no event when the course was already placed (store dedup)", () => {
    placeTracked("360744", "detail");
    gtag.mockClear();
    const outcome = placeTracked("360744", "slot");
    expect(outcome.added).toBe(false);
    expect(gtag).not.toHaveBeenCalled();
  });

  it("buckets the placed count instead of sending the exact number", () => {
    for (const id of ["1", "2", "3", "4", "5", "6"]) placeTracked(id, "slot");
    const buckets = eventsNamed("course_added").map((c) => (c[2] as Record<string, unknown>).placed_count_bucket);
    expect(buckets).toEqual(["1", "2_5", "2_5", "2_5", "2_5", "6_plus"]);
  });

  it("never sends an offering_id", () => {
    placeTracked("360744", "detail");
    expect(JSON.stringify(gtag.mock.calls)).not.toContain("360744");
  });
});

describe("plan_created", () => {
  it("fires exactly once, on the real 0 -> 1 transition", () => {
    placeTracked("360744", "course_list");
    expect(eventsNamed("plan_created")).toHaveLength(1);
    expect(eventsNamed("plan_created")[0][2]).toEqual({
      site_surface: "course",
      term_key: "115-1",
      placement: "course_list",
    });

    placeTracked("360745", "slot");
    expect(eventsNamed("plan_created")).toHaveLength(1);
  });

  it("does not fire again after the user empties and refills the same term (session guard)", () => {
    placeTracked("360744", "course_list");
    useDraftStore.setState({ placed: [] });
    gtag.mockClear();
    placeTracked("360744", "course_list");
    expect(eventsNamed("plan_created")).toHaveLength(0);
    expect(eventsNamed("course_added")).toHaveLength(1); // 排課本身照常量測
  });

  it("is not triggered by localStorage rehydration or a term switch (no user action)", () => {
    // rehydrate = 直接 setState，一門都不經過 placeTracked。
    useDraftStore.setState({ placed: [{ offering_id: "360744", priority: 1 }] });
    useTermStore.setState({ termKey: "114-2" });
    expect(eventsNamed("plan_created")).toHaveLength(0);
  });

  it("covers the shared-import merge and replace paths via the transition helper", () => {
    trackPlanCreatedTransition(0, 3, "shared_import");
    expect(eventsNamed("plan_created")).toHaveLength(1);
    expect((eventsNamed("plan_created")[0][2] as Record<string, unknown>).placement).toBe("shared_import");

    // 非 0 起點（合併到已有課表）→ 不是建立第一份課表。
    gtag.mockClear();
    trackPlanCreatedTransition(2, 5, "shared_import");
    expect(eventsNamed("plan_created")).toHaveLength(0);
  });

  it("tracks the guard per term", () => {
    placeTracked("360744", "detail");
    useTermStore.setState({ termKey: "114-2" });
    useDraftStore.setState({ placed: [] });
    gtag.mockClear();
    placeTracked("360744", "detail");
    expect(eventsNamed("plan_created")).toHaveLength(1);
    expect((eventsNamed("plan_created")[0][2] as Record<string, unknown>).term_key).toBe("114-2");
  });
});

describe("analytics failures never break placing", () => {
  it("still places the course when gtag throws", () => {
    window.gtag = (() => {
      throw new Error("blocked by extension");
    }) as unknown as typeof window.gtag;
    expect(() => placeTracked("360744", "course_list")).not.toThrow();
    expect(useDraftStore.getState().placed.map((p) => p.offering_id)).toEqual(["360744"]);
  });
});
