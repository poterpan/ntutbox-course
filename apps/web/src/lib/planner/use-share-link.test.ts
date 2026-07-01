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

  it("strips the share params from the URL so refresh doesn't re-trigger", () => {
    window.history.replaceState({}, "", "/?term=115-1&course=360744");
    renderHook(() => useShareLink());
    expect(window.location.search).not.toContain("course=");
    expect(window.location.search).not.toContain("term=");
  });

  it("opens the shared-plan overlay for a ?plan link, without touching detail/draft", () => {
    window.history.replaceState({}, "", "/?term=114-2&plan=360744.360745.360763");
    renderHook(() => useShareLink());
    const ui = useUiStore.getState();
    expect(ui.selectedTerm).toBe("114-2");
    expect(ui.sharedPlan).toEqual({ termKey: "114-2", offeringIds: ["360744", "360745", "360763"] });
    expect(ui.sharedPlanOpen).toBe(true);
    expect(ui.detailOfferingId).toBeNull();
    expect(window.location.search).not.toContain("plan=");
  });
});
