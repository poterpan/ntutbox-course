import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MicroProgramList } from "./MicroProgramList";
import { useUiStore } from "@/store/ui-store";
import { useMprograms } from "@/lib/planner/use-mprograms";
import { OAA_MPROGRAM_URL } from "@/lib/planner/mprogram-links";

vi.mock("@/lib/planner/use-mprograms", () => ({ useMprograms: vi.fn() }));
const mocked = vi.mocked(useMprograms);
const dir = {
  schema_version: 2,
  term_key: "115-1",
  programs: [
    { code: "AV2", name: "面板微學程", offering_ids: ["1", "2"], courses: [], rules_text: null },
    { code: "AV3", name: "創業家精神微學程", offering_ids: ["3"], courses: [], rules_text: null },
  ],
} as never;

beforeEach(() => useUiStore.setState({ selectedProgramCode: null }));

describe("MicroProgramList", () => {
  it("列出學程、點列選入", () => {
    mocked.mockReturnValue({ data: dir, loading: false, error: false, retry: vi.fn() });
    render(<MicroProgramList />);
    expect(screen.getByText("2 門開課")).toBeInTheDocument();
    fireEvent.click(screen.getByText("面板微學程"));
    expect(useUiStore.getState().selectedProgramCode).toBe("AV2");
    expect(screen.getByRole("link", { name: /教務處/ })).toHaveAttribute("href", OAA_MPROGRAM_URL);
  });

  it("過濾", () => {
    mocked.mockReturnValue({ data: dir, loading: false, error: false, retry: vi.fn() });
    render(<MicroProgramList />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "創業" } });
    expect(screen.queryByText("面板微學程")).toBeNull();
  });

  it("error 態可重試", () => {
    const retry = vi.fn();
    mocked.mockReturnValue({ data: null, loading: false, error: true, retry });
    render(<MicroProgramList />);
    fireEvent.click(screen.getByRole("button", { name: /重試/ }));
    expect(retry).toHaveBeenCalled();
  });
});
