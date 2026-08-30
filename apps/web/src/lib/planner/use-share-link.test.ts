import { renderHook, act } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useShareLink } from "./use-share-link";
import { useUiStore } from "@/store/ui-store";
import { useTermStore } from "@/store/term-store";
import { useToast } from "@/components/ui/toast";
import type { CourseOffering, TermBundle } from "@/lib/data/types";

function bundleWith(ids: string[]): TermBundle {
  return {
    catalog: { courses: ids.map((id) => ({ offering_id: id } as unknown as CourseOffering)) },
  } as unknown as TermBundle;
}

beforeEach(() => {
  useUiStore.setState({ detailOfferingId: null, selectedTerm: "115-1", sharedPlan: null, sharedPlanOpen: false });
  useTermStore.setState({ status: "idle", termKey: null, bundle: null });
  useToast.setState({ message: null });
  window.history.replaceState({}, "", "/");
});

describe("useShareLink", () => {
  it("does nothing without share params", () => {
    renderHook(() => useShareLink());
    expect(useUiStore.getState().detailOfferingId).toBeNull();
    expect(useToast.getState().message).toBeNull();
  });

  it("sets the target term and opens the detail once that term is loaded", () => {
    window.history.replaceState({}, "", "/?term=114-2&course=360744");
    renderHook(() => useShareLink());
    expect(useUiStore.getState().selectedTerm).toBe("114-2");

    act(() => {
      useTermStore.setState({ status: "ready", termKey: "114-2", bundle: bundleWith(["360744"]) });
    });
    expect(useUiStore.getState().detailOfferingId).toBe("360744");
    expect(useToast.getState().message).toBeNull();
  });

  it("toasts not-found when the shared course is absent from the term", () => {
    window.history.replaceState({}, "", "/?term=115-1&course=999999");
    renderHook(() => useShareLink());
    act(() => {
      useTermStore.setState({ status: "ready", termKey: "115-1", bundle: bundleWith(["360744"]) });
    });
    expect(useUiStore.getState().detailOfferingId).toBeNull();
    expect(useToast.getState().message).toBeTruthy();
  });

  it("keeps the share params in the URL so the address stays shareable", () => {
    // 過去這裡會 replaceState 清掉參數，導致：① 使用者複製到的網址是首頁；
    // ② Googlebot 渲染後 location 變成 "/"，2,461 個課程 URL 在索引端無法區分。
    window.history.replaceState({}, "", "/?term=115-1&course=360744");
    renderHook(() => useShareLink());
    expect(window.location.search).toContain("course=360744");
    expect(window.location.search).toContain("term=115-1");
  });

  it("does not re-open the detail after the user closes it (no re-trigger loop)", () => {
    window.history.replaceState({}, "", "/?term=115-1&course=360744");
    renderHook(() => useShareLink());
    act(() => {
      useTermStore.setState({ status: "ready", termKey: "115-1", bundle: bundleWith(["360744"]) });
    });
    expect(useUiStore.getState().detailOfferingId).toBe("360744");
    // 使用者關窗後，參數仍在 URL 上，但不應再度自動開窗
    act(() => useUiStore.setState({ detailOfferingId: null }));
    act(() => {
      useTermStore.setState({ status: "ready", termKey: "115-1", bundle: bundleWith(["360744"]) });
    });
    expect(useUiStore.getState().detailOfferingId).toBeNull();
  });

  it("opens the shared-plan overlay for a ?plan link, without touching detail/draft", () => {
    window.history.replaceState({}, "", "/?term=114-2&plan=360744.360745.360763");
    renderHook(() => useShareLink());
    const ui = useUiStore.getState();
    expect(ui.selectedTerm).toBe("114-2");
    expect(ui.sharedPlan).toEqual({ termKey: "114-2", offeringIds: ["360744", "360745", "360763"] });
    expect(ui.sharedPlanOpen).toBe(true);
    expect(ui.detailOfferingId).toBeNull();
    // plan 參數同樣保留：分享課表的網址要能被複製轉傳。
    // （SEO 上 plan 是無限排列組合，由 worker 一律 canonical 回首頁，見 lib/share/og.ts）
    expect(window.location.search).toContain("plan=");
  });
});
