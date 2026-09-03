import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExportToAppDialog } from "./ExportToAppDialog";
import { useDraftStore } from "@/store/draft-store";
import { useTermStore } from "@/store/term-store";
import { resetAnalyticsState } from "@/lib/analytics";
import { CONSENT_COOKIE, CONSENT_GRANTED } from "@/lib/analytics/consent";
import { resetSessionFallback } from "@/lib/analytics/storage";
import { encodePlanPayload } from "@/lib/share/plan-payload";
import type { CourseOffering } from "@/lib/data/types";

// 只覆寫 encodePlanPayload（讓個別測試控制成功/失敗/壓縮與否），buildPlanPayload /
// buildPlanHandoffURL 走真實實作——這兩個是純函式，沒有必要 mock。
vi.mock("@/lib/share/plan-payload", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/share/plan-payload")>();
  return { ...actual, encodePlanPayload: vi.fn(actual.encodePlanPayload) };
});

// jsdom 無 matchMedia；沿用 PlannerLayout.test.tsx 的做法模擬 touch/桌機判定。
function mockMatchMedia(matches: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches, media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  })) as never;
}

// 刻意帶有可識別字串的課程資料：課名／教師名／offering_id 都要能在「不外洩」測試裡當
// 反例字串比對。
const calc = {
  offering_id: "360744",
  name: { zh: "微積分（一）" },
  credits: 3,
  teachers: [{ code: "T1", name: "王小明" }],
  classrooms: [{ code: "R1", name: "綜科館 502" }],
  requirement: { category: "required" },
  meetings: [{ day: 1, periods: ["7", "8"] }],
} as unknown as CourseOffering;

let gtag: ReturnType<typeof vi.fn>;

function eventsNamed(name: string) {
  return gtag.mock.calls.filter((c) => c[0] === "event" && c[1] === name);
}

function seedStores() {
  useDraftStore.setState({
    termKey: "115-1",
    favorites: [],
    placed: [{ offering_id: "360744", priority: 1 }],
  });
  useTermStore.setState({
    status: "ready",
    termKey: "115-1",
    error: null,
    generation: 1,
    bundle: {
      termKey: "115-1",
      catalog: { courses: [calc], freshness: null } as never,
      periods: { periods: [] } as never,
      classes: { classes: [] } as never,
      enrollment: null,
    } as never,
  });
}

beforeEach(() => {
  resetAnalyticsState();
  resetSessionFallback();
  window.sessionStorage.clear();
  vi.stubEnv("NEXT_PUBLIC_GA_MEASUREMENT_ID", "G-TEST123");
  vi.stubEnv("NEXT_PUBLIC_GA_ENABLED", "true");
  vi.stubEnv("NEXT_PUBLIC_GA_DEBUG", "true"); // jsdom host = localhost
  document.cookie = `${CONSENT_COOKIE}=${CONSENT_GRANTED}; Path=/`;
  gtag = vi.fn();
  window.gtag = gtag as unknown as typeof window.gtag;
  vi.mocked(encodePlanPayload).mockClear();
  seedStores();
});

afterEach(() => {
  vi.unstubAllEnvs();
  document.cookie = `${CONSENT_COOKIE}=; Path=/; Max-Age=0`;
  delete window.gtag;
  delete (window as { matchMedia?: unknown }).matchMedia;
});

describe("手機分支：<a href> 點擊送出 universal_link", () => {
  it("export_to_app_click 參數逐欄相符，沒有多餘欄位", async () => {
    mockMatchMedia(true); // 觸控裝置 → 手機分支
    render(<ExportToAppDialog open={true} onOpenChange={() => {}} />);

    const link = await screen.findByRole("link", { name: /在 App 中開啟/ });
    await userEvent.click(link);

    const calls = eventsNamed("export_to_app_click");
    expect(calls).toHaveLength(1);
    // 精確比對而非「包含」——未來多送任何欄位（例如不小心加了 payload 相關欄位）都會讓這裡變紅。
    expect(calls[0][2]).toEqual({
      site_surface: "course",
      term_key: "115-1",
      handoff_method: "universal_link",
      course_count_bucket: "1",
    });
  });
});

describe("payload 不外洩到 analytics（唯一不可逆風險）", () => {
  it("export_to_app_click 不含課名／課號／教師名，也不含連結 fragment 本身", async () => {
    mockMatchMedia(true);
    render(<ExportToAppDialog open={true} onOpenChange={() => {}} />);

    const link = await screen.findByRole("link", { name: /在 App 中開啟/ });
    const href = link.getAttribute("href") ?? "";
    const fragment = href.split("#")[1] ?? "";
    // 確認真的抓到編碼後的內容（不是抓到空字串才通過，那樣這條測試沒有意義）。
    expect(fragment.length).toBeGreaterThan(20);

    await userEvent.click(link);

    const raw = JSON.stringify(gtag.mock.calls);
    expect(raw).not.toContain(fragment); // 編碼後的 payload 片段本身
    expect(raw).not.toContain("360744"); // offering_id（課號）
    expect(raw).not.toContain("微積分"); // 課名
    expect(raw).not.toContain("王小明"); // 教師名
  });
});

describe("編碼失敗", () => {
  it("送 export_to_app_error(payload_build_failed)，且不留舊連結給使用者點/複製", async () => {
    vi.mocked(encodePlanPayload).mockRejectedValueOnce(new Error("boom"));
    render(<ExportToAppDialog open={true} onOpenChange={() => {}} />);

    await screen.findByText("連結產生失敗，請重新整理頁面再試一次。");

    const calls = eventsNamed("export_to_app_error");
    expect(calls).toHaveLength(1);
    expect(calls[0][2]).toEqual({
      site_surface: "course",
      term_key: "115-1",
      error_code: "payload_build_failed",
    });
    // url 維持 null：複製鈕停用、也不會顯示手機/QR 任何一條路。
    expect(screen.getByRole("button", { name: /複製連結/ })).toBeDisabled();
    expect(screen.queryByRole("link", { name: /在 App 中開啟/ })).not.toBeInTheDocument();
  });
});

describe("未壓縮時隱藏 QR（密度過高不好掃）", () => {
  it("compressed=false 時不顯示 QR、改顯示提示文字，複製連結仍可用", async () => {
    vi.mocked(encodePlanPayload).mockResolvedValueOnce({ encoded: "short-and-uncompressed", compressed: false });
    // 桌機情境：不 stub matchMedia（jsdom 預設沒有 matchMedia → isTouchPrimary() 回 false）。
    render(<ExportToAppDialog open={true} onOpenChange={() => {}} />);

    await screen.findByText(/這份課表的連結較長/);
    expect(screen.queryByText(/用手機相機掃這個 QR/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /複製連結/ })).not.toBeDisabled();
  });
});
