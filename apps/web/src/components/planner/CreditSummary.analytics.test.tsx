import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CreditSummary } from "./CreditSummary";
import { useDraftStore } from "@/store/draft-store";
import { useTermStore } from "@/store/term-store";
import { useToast } from "@/components/ui/toast";
import { resetAnalyticsState } from "@/lib/analytics";
import { CONSENT_COOKIE, CONSENT_GRANTED } from "@/lib/analytics/consent";
import type { ShareResult } from "@/lib/share/share-course";

const shareResult = vi.hoisted(() => ({ current: "copied" as ShareResult }));
vi.mock("@/lib/share/share-course", () => ({
  shareOrCopy: vi.fn(async () => shareResult.current),
}));

const courses = [
  { offering_id: "360744", name: { zh: "微積分" }, credits: 3, teachers: [], meetings: [{ day: 1, periods: ["1"] }], classes: [] },
  { offering_id: "360745", name: { zh: "演算法" }, credits: 3, teachers: [], meetings: [{ day: 3, periods: ["5"] }], classes: [] },
];

let gtag: ReturnType<typeof vi.fn>;

function eventsNamed(name: string) {
  return gtag.mock.calls.filter((c) => c[0] === "event" && c[1] === name);
}

beforeEach(() => {
  resetAnalyticsState();
  vi.stubEnv("NEXT_PUBLIC_GA_MEASUREMENT_ID", "G-TEST123");
  vi.stubEnv("NEXT_PUBLIC_GA_ENABLED", "true");
  vi.stubEnv("NEXT_PUBLIC_GA_DEBUG", "true"); // jsdom host = localhost
  document.cookie = `${CONSENT_COOKIE}=${CONSENT_GRANTED}; Path=/`;
  gtag = vi.fn();
  window.gtag = gtag as unknown as typeof window.gtag;
  shareResult.current = "copied";
  useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] });
  useTermStore.setState({
    status: "ready", termKey: "115-1", error: null, generation: 1,
    bundle: { termKey: "115-1", catalog: { courses } as never, periods: { periods: [] } as never, classes: { classes: [] } as never, enrollment: null } as never,
  });
  useToast.setState({ message: null });
});

afterEach(() => {
  vi.unstubAllEnvs();
  document.cookie = `${CONSENT_COOKIE}=; Path=/; Max-Age=0`;
  delete window.gtag;
});

describe("匯出到 App（開啟 ExportToAppDialog）", () => {
  // F-C 佔位鈕已換成真流程（ExportToAppDialog）。CreditSummary 這層只負責「開窗」，
  // 真正的 export_to_app_click / export_to_app_error 追蹤（何時送、handoff_method 為何）
  // 是 ExportToAppDialog 自己的責任與測試範圍，這裡不斷言那些事件。
  it("clicking opens the dialog when a plan exists", async () => {
    useDraftStore.setState({ placed: [{ offering_id: "360744", priority: 1 }, { offering_id: "360745", priority: 2 }] });
    render(<CreditSummary />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /匯出到 App/ }));
    expect(await screen.findByRole("dialog", { name: "匯入到北科盒子" })).toBeInTheDocument();
  });

  it("disables the button for an empty plan, so the dialog never opens", async () => {
    render(<CreditSummary />);
    const button = screen.getByRole("button", { name: /匯出到 App/ });
    expect(button).toBeDisabled();
    // 不只驗 disabled 屬性——實際嘗試點擊，確認空課表真的開不了窗（這是唯一的
    // guard：ExportToAppDialog 本身對 0 門課不會拒絕，見 team-lead 對這條的補充要求）。
    await userEvent.click(button);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("plan_shared（課表分享）", () => {
  it("maps a native share to web_share", async () => {
    shareResult.current = "shared";
    useDraftStore.setState({ placed: [{ offering_id: "360744", priority: 1 }] });
    render(<CreditSummary />);
    await userEvent.click(screen.getByRole("button", { name: /分享課表/ }));
    expect(eventsNamed("plan_shared")[0][2]).toEqual({
      site_surface: "course",
      term_key: "115-1",
      share_method: "web_share",
      course_count_bucket: "1",
    });
  });

  it("maps a clipboard copy to copy and keeps the toast", async () => {
    shareResult.current = "copied";
    useDraftStore.setState({ placed: [{ offering_id: "360744", priority: 1 }] });
    render(<CreditSummary />);
    await userEvent.click(screen.getByRole("button", { name: /分享課表/ }));
    expect((eventsNamed("plan_shared")[0][2] as Record<string, unknown>).share_method).toBe("copy");
    expect(useToast.getState().message).toBe("已複製課表連結");
  });

  it("sends nothing when sharing failed, and still surfaces the failure toast", async () => {
    shareResult.current = "failed";
    useDraftStore.setState({ placed: [{ offering_id: "360744", priority: 1 }] });
    render(<CreditSummary />);
    await userEvent.click(screen.getByRole("button", { name: /分享課表/ }));
    expect(eventsNamed("plan_shared")).toHaveLength(0);
    expect(useToast.getState().message).toBe("複製失敗，請手動複製網址");
  });

  it("never sends offering IDs", async () => {
    useDraftStore.setState({ placed: [{ offering_id: "360744", priority: 1 }] });
    render(<CreditSummary />);
    await userEvent.click(screen.getByRole("button", { name: /分享課表/ }));
    expect(JSON.stringify(gtag.mock.calls)).not.toContain("360744");
  });
});
