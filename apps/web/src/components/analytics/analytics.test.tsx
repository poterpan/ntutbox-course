import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AnalyticsConsent } from "./AnalyticsConsent";
import { GoogleAnalytics } from "./GoogleAnalytics";
import { useConsentStore } from "@/store/consent-store";
import { resetAnalyticsState } from "@/lib/analytics";
import { CONSENT_COOKIE, CONSENT_DENIED, CONSENT_GRANTED, readConsent } from "@/lib/analytics/consent";

// next/script 在 jsdom 沒有 App Router 的注入環境，換成一個看得見的節點，才能斷言
// 「同意前完全沒有 googletagmanager 引用」。（不用真的 <script>：那會踩 no-sync-scripts。）
vi.mock("next/script", () => ({
  default: ({ src, id }: { src: string; id?: string }) => (
    <div data-testid="ga-script" data-id={id} data-src={src} />
  ),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

function enableGa() {
  vi.stubEnv("NEXT_PUBLIC_GA_MEASUREMENT_ID", "G-TEST123");
  vi.stubEnv("NEXT_PUBLIC_GA_ENABLED", "true");
  vi.stubEnv("NEXT_PUBLIC_GA_DEBUG", "true"); // jsdom host = localhost
}

beforeEach(() => {
  resetAnalyticsState();
  document.cookie = `${CONSENT_COOKIE}=; Path=/; Max-Age=0`;
  useConsentStore.setState({ consent: "unknown", hydrated: false });
  window.dataLayer = [];
  window.gtag = vi.fn() as unknown as typeof window.gtag;
});

afterEach(() => {
  vi.unstubAllEnvs();
  delete window.gtag;
  delete window.dataLayer;
});

describe("AnalyticsConsent", () => {
  it("renders nothing when GA env is absent (現狀行為完全不變)", () => {
    render(<AnalyticsConsent />);
    expect(screen.queryByRole("region", { name: "成效分析同意" })).toBeNull();
  });

  it("offers 同意 and 拒絕 as equally sized buttons, plus a privacy link", () => {
    enableGa();
    render(<AnalyticsConsent />);
    const grant = screen.getByRole("button", { name: "同意" });
    const deny = screen.getByRole("button", { name: "拒絕" });
    // 同等可見：AccentButton 兩個 tone 共用同一組 size token，只差色調。
    expect(grant.className).toContain("flex-1");
    expect(deny.className).toContain("flex-1");
    expect(grant.className.replace("solid", "")).not.toBe("");
    const link = screen.getByRole("link", { name: /隱私/ });
    expect(link).toHaveAttribute("href", "https://ntutbox.com/privacy/");
  });

  it("writes granted_v1 on 同意 and hides itself", async () => {
    enableGa();
    render(<AnalyticsConsent />);
    await userEvent.click(screen.getByRole("button", { name: "同意" }));
    expect(readConsent()).toBe("granted");
    expect(document.cookie).toContain(`${CONSENT_COOKIE}=${CONSENT_GRANTED}`);
    expect(screen.queryByRole("button", { name: "同意" })).toBeNull();
  });

  it("writes denied_v1 on 拒絕 and stays hidden afterwards", async () => {
    enableGa();
    render(<AnalyticsConsent />);
    await userEvent.click(screen.getByRole("button", { name: "拒絕" }));
    expect(readConsent()).toBe("denied");
    expect(document.cookie).toContain(`${CONSENT_COOKIE}=${CONSENT_DENIED}`);

    useConsentStore.setState({ hydrated: false });
    render(<AnalyticsConsent />);
    expect(screen.queryByRole("button", { name: "同意" })).toBeNull();
  });

  it("does not ask again once a decision exists", () => {
    enableGa();
    document.cookie = `${CONSENT_COOKIE}=${CONSENT_GRANTED}; Path=/`;
    render(<AnalyticsConsent />);
    expect(screen.queryByRole("button", { name: "同意" })).toBeNull();
  });
});

describe("GoogleAnalytics loader", () => {
  it("loads no Google script before consent", () => {
    enableGa();
    render(<GoogleAnalytics />);
    expect(screen.queryByTestId("ga-script")).toBeNull();
    expect(document.querySelector('script[src*="googletagmanager.com"]')).toBeNull();
  });

  it("loads no Google script after an explicit denial", () => {
    enableGa();
    document.cookie = `${CONSENT_COOKIE}=${CONSENT_DENIED}; Path=/`;
    render(<GoogleAnalytics />);
    expect(screen.queryByTestId("ga-script")).toBeNull();
  });

  it("loads gtag.js and sends a page_view once consent is granted", () => {
    enableGa();
    document.cookie = `${CONSENT_COOKIE}=${CONSENT_GRANTED}; Path=/`;
    render(<GoogleAnalytics />);
    expect(screen.getByTestId("ga-script")).toHaveAttribute(
      "data-src",
      "https://www.googletagmanager.com/gtag/js?id=G-TEST123",
    );
    const calls = (window.gtag as unknown as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls.some((c) => c[0] === "config")).toBe(true);
    expect(calls.filter((c) => c[0] === "event" && c[1] === "page_view")).toHaveLength(1);
  });

  it("loads nothing when the env is absent, even with consent granted", () => {
    document.cookie = `${CONSENT_COOKIE}=${CONSENT_GRANTED}; Path=/`;
    render(<GoogleAnalytics />);
    expect(screen.queryByTestId("ga-script")).toBeNull();
  });
});

describe("revoke", () => {
  it("denies consent and clears the front-end-deletable Google cookies", () => {
    enableGa();
    document.cookie = `${CONSENT_COOKIE}=${CONSENT_GRANTED}; Path=/`;
    document.cookie = "_ga=GA1.1.1.1; Path=/";
    document.cookie = "_ga_TEST=GS1.1.1; Path=/";
    document.cookie = "_gcl_au=1.1.1.1; Path=/";

    useConsentStore.getState().revoke();

    expect(readConsent()).toBe("denied");
    expect(document.cookie).not.toContain("_ga=");
    expect(document.cookie).not.toContain("_ga_TEST");
    expect(document.cookie).not.toContain("_gcl_au");
    expect(useConsentStore.getState().consent).toBe("denied");
  });
});
