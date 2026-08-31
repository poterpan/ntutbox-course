import { renderHook, act } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useCourseTitle, HOME_TITLE } from "./use-course-title";
import { useUiStore } from "@/store/ui-store";
import { useTermStore } from "@/store/term-store";
import type { CourseOffering, TermBundle } from "@/lib/data/types";

function bundleWith(rows: Array<[string, string]>): TermBundle {
  return {
    catalog: {
      courses: rows.map(([id, zh]) => ({ offering_id: id, name: { zh } } as unknown as CourseOffering)),
    },
  } as unknown as TermBundle;
}

beforeEach(() => {
  useUiStore.setState({ detailOfferingId: null });
  useTermStore.setState({
    status: "ready",
    termKey: "115-1",
    bundle: bundleWith([["360744", "國文"], ["360745", "英文"]]),
  });
  document.title = HOME_TITLE;
});

describe("useCourseTitle", () => {
  it("sets the course name as title while a detail is open", () => {
    renderHook(() => useCourseTitle());
    act(() => useUiStore.setState({ detailOfferingId: "360744" }));
    expect(document.title).toBe("國文｜北科盒子 排課");
  });

  it("restores the home title when the detail is closed", () => {
    renderHook(() => useCourseTitle());
    act(() => useUiStore.setState({ detailOfferingId: "360744" }));
    act(() => useUiStore.setState({ detailOfferingId: null }));
    expect(document.title).toBe(HOME_TITLE);
  });

  it("follows the title when switching from one course to another", () => {
    renderHook(() => useCourseTitle());
    act(() => useUiStore.setState({ detailOfferingId: "360744" }));
    act(() => useUiStore.setState({ detailOfferingId: "360745" }));
    expect(document.title).toBe("英文｜北科盒子 排課");
  });

  it("keeps the home title for an offering the term does not contain", () => {
    renderHook(() => useCourseTitle());
    act(() => useUiStore.setState({ detailOfferingId: "999999" }));
    expect(document.title).toBe(HOME_TITLE);
  });

  it("restores the home title on unmount", () => {
    const { unmount } = renderHook(() => useCourseTitle());
    act(() => useUiStore.setState({ detailOfferingId: "360744" }));
    unmount();
    expect(document.title).toBe(HOME_TITLE);
  });

  it("does not clobber a title someone else set before unmount", () => {
    // 實測回歸：從首頁 client-side 導航到 /browse/ 時，Next 會先套上 hub 頁的
    // metadata title，planner 才卸載——無條件還原會把 hub 頁的標題蓋回首頁標題。
    const { unmount } = renderHook(() => useCourseTitle());
    act(() => useUiStore.setState({ detailOfferingId: "360744" }));
    document.title = "北科大課程總覽・依系所瀏覽（115-1）｜北科盒子 排課";
    unmount();
    expect(document.title).toBe("北科大課程總覽・依系所瀏覽（115-1）｜北科盒子 排課");
  });
});
