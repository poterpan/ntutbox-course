import { describe, it, expect, beforeEach } from "vitest";
import { useUiStore } from "./ui-store";

describe("ui-store — 微學程 tab", () => {
  beforeEach(() =>
    useUiStore.setState({ libraryTab: "courses", selectedProgramCode: null, detailOfferingId: null, libraryOpen: false })
  );

  it("initial selectedProgramCode is null", () => {
    expect(useUiStore.getState().selectedProgramCode).toBeNull();
  });

  it("setSelectedProgramCode updates the code", () => {
    useUiStore.getState().setSelectedProgramCode("AV2");
    expect(useUiStore.getState().selectedProgramCode).toBe("AV2");
    useUiStore.getState().setSelectedProgramCode(null);
    expect(useUiStore.getState().selectedProgramCode).toBeNull();
  });

  it("openProgram switches tab, opens panel, closes detail", () => {
    useUiStore.setState({ libraryTab: "courses", detailOfferingId: "x", libraryOpen: false });
    useUiStore.getState().openProgram("AV2");
    const s = useUiStore.getState();
    expect(s.libraryTab).toBe("programs");
    expect(s.selectedProgramCode).toBe("AV2");
    expect(s.libraryOpen).toBe(true);
    expect(s.detailOfferingId).toBeNull();
  });
});
