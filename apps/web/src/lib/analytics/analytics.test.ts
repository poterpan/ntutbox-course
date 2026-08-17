import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { bootstrapConsentMode, configureGa, resetAnalyticsState, trackEvent, trackPageView } from ".";
import { CONSENT_COOKIE, CONSENT_DENIED, CONSENT_GRANTED } from "./consent";
import { isAllowedHost } from "./config";

// jsdom 的 host 是 localhost（不在 production allowlist），所以測試一律開 debug 逃生門
// 來模擬「允許的 host」，另有一個測試專門驗 allowlist 本身。
function enableGa({ debug = true }: { debug?: boolean } = {}) {
  vi.stubEnv("NEXT_PUBLIC_GA_MEASUREMENT_ID", "G-TEST123");
  vi.stubEnv("NEXT_PUBLIC_GA_ENABLED", "true");
  if (debug) vi.stubEnv("NEXT_PUBLIC_GA_DEBUG", "true");
}

function setConsent(value: string | null) {
  document.cookie = value
    ? `${CONSENT_COOKIE}=${value}; Path=/`
    : `${CONSENT_COOKIE}=; Path=/; Max-Age=0`;
}

let gtag: ReturnType<typeof vi.fn>;

beforeEach(() => {
  resetAnalyticsState();
  setConsent(null);
  window.dataLayer = [];
  gtag = vi.fn();
  window.gtag = gtag as unknown as typeof window.gtag;
});

afterEach(() => {
  vi.unstubAllEnvs();
  delete window.gtag;
  delete window.dataLayer;
});

describe("trackEvent gating", () => {
  it("no-ops when the measurement ID is absent (env 未設 = 全站現狀)", () => {
    vi.stubEnv("NEXT_PUBLIC_GA_ENABLED", "true");
    vi.stubEnv("NEXT_PUBLIC_GA_DEBUG", "true");
    setConsent(CONSENT_GRANTED);
    trackEvent("plan_created", { term_key: "115-1", placement: "detail" });
    expect(gtag).not.toHaveBeenCalled();
  });

  it("no-ops when NEXT_PUBLIC_GA_ENABLED is not true", () => {
    vi.stubEnv("NEXT_PUBLIC_GA_MEASUREMENT_ID", "G-TEST123");
    vi.stubEnv("NEXT_PUBLIC_GA_DEBUG", "true");
    setConsent(CONSENT_GRANTED);
    trackEvent("plan_created", { term_key: "115-1", placement: "detail" });
    expect(gtag).not.toHaveBeenCalled();
  });

  it("no-ops before consent and after an explicit denial", () => {
    enableGa();
    trackEvent("plan_created", { term_key: "115-1", placement: "detail" });
    expect(gtag).not.toHaveBeenCalled();

    setConsent(CONSENT_DENIED);
    trackEvent("plan_created", { term_key: "115-1", placement: "detail" });
    expect(gtag).not.toHaveBeenCalled();
  });

  it("no-ops on a host outside the allowlist", () => {
    enableGa({ debug: false }); // debug 關閉 → localhost 不在 allowlist
    setConsent(CONSENT_GRANTED);
    trackEvent("plan_created", { term_key: "115-1", placement: "detail" });
    expect(gtag).not.toHaveBeenCalled();

    expect(isAllowedHost("course.ntutbox.com")).toBe(true);
    expect(isAllowedHost("ntutbox.com")).toBe(true);
    expect(isAllowedHost("www.ntutbox.com")).toBe(true);
    expect(isAllowedHost("ntutbox-course-web.workers.dev")).toBe(false);
    expect(isAllowedHost("localhost")).toBe(false);
  });

  it("sends the event with site_surface once granted", () => {
    enableGa();
    setConsent(CONSENT_GRANTED);
    trackEvent("course_added", { term_key: "115-1", placement: "slot", placed_count_bucket: "2_5" });
    expect(gtag).toHaveBeenCalledWith("event", "course_added", {
      site_surface: "course",
      term_key: "115-1",
      placement: "slot",
      placed_count_bucket: "2_5",
    });
  });

  it("drops params outside the event's allowlist at runtime", () => {
    enableGa();
    setConsent(CONSENT_GRANTED);
    trackEvent("course_search", {
      term_key: "115-1",
      result_bucket: "1_10",
      filter_count_bucket: "1",
      // 型別擋得住，但 runtime 也必須丟掉（例如未來重構誤傳）。
      query: "微積分",
      offering_id: "360744",
    } as never);
    const params = gtag.mock.calls[0][2] as Record<string, unknown>;
    expect(params.query).toBeUndefined();
    expect(params.offering_id).toBeUndefined();
    expect(params).toEqual({
      site_surface: "course",
      term_key: "115-1",
      result_bucket: "1_10",
      filter_count_bucket: "1",
    });
  });

  it("swallows a throwing gtag so analytics can never break a product action", () => {
    enableGa();
    setConsent(CONSENT_GRANTED);
    window.gtag = (() => {
      throw new Error("gtag blew up");
    }) as unknown as typeof window.gtag;
    expect(() => trackEvent("plan_shared", { term_key: "115-1", share_method: "copy", course_count_bucket: "1" })).not.toThrow();
  });
});

describe("consent bootstrap", () => {
  it("queues Consent Mode v2 defaults as denied without loading any Google resource", () => {
    enableGa();
    bootstrapConsentMode();
    expect(gtag).toHaveBeenCalledWith("consent", "default", {
      analytics_storage: "denied",
      ad_storage: "denied",
      ad_user_data: "denied",
      ad_personalization: "denied",
    });
    expect(document.querySelector('script[src*="googletagmanager.com"]')).toBeNull();
  });

  it("configures with send_page_view:false and sanitized page fields", () => {
    enableGa();
    setConsent(CONSENT_GRANTED);
    window.history.replaceState({}, "", "/?term=115-1&plan=360744.360745");
    configureGa();
    const [command, id, params] = gtag.mock.calls.find((c) => c[0] === "config")!;
    expect(command).toBe("config");
    expect(id).toBe("G-TEST123");
    const config = params as Record<string, unknown>;
    expect(config.send_page_view).toBe(false);
    expect(config.cookie_domain).toBe("auto");
    expect(String(config.page_location)).not.toContain("plan=");
    expect(config.term_key).toBeUndefined(); // term_key 是事件參數，不當全域參數
  });
});

describe("trackPageView", () => {
  it("sets sanitized page fields globally and sends page_view with term_key", () => {
    enableGa();
    setConsent(CONSENT_GRANTED);
    window.history.replaceState({}, "", "/?term=115-1&plan=360744&utm_source=google");
    trackPageView();

    const setCall = gtag.mock.calls.find((c) => c[0] === "set")!;
    const fields = setCall[1] as Record<string, unknown>;
    expect(String(fields.page_location)).toContain("utm_source=google");
    expect(String(fields.page_location)).not.toContain("plan=");
    expect(String(fields.page_location)).not.toContain("term=");
    expect(fields.term_key).toBeUndefined();

    expect(gtag).toHaveBeenCalledWith("event", "page_view", { site_surface: "course", term_key: "115-1" });
  });

  it("no-ops entirely without consent", () => {
    enableGa();
    trackPageView();
    expect(gtag).not.toHaveBeenCalled();
  });

  it("does not repeat the same page twice (StrictMode / remount), but does send a real route change", () => {
    enableGa();
    setConsent(CONSENT_GRANTED);
    window.history.replaceState({}, "", "/");
    trackPageView();
    trackPageView();
    expect(gtag.mock.calls.filter((c) => c[1] === "page_view")).toHaveLength(1);

    window.history.replaceState({}, "", "/?utm_source=google");
    trackPageView();
    expect(gtag.mock.calls.filter((c) => c[1] === "page_view")).toHaveLength(2);
  });
});
