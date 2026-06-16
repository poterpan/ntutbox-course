import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FilterBar } from "./FilterBar";
import { useUiStore } from "@/store/ui-store";
import { EMPTY_FILTER } from "@/lib/filters/types";

beforeEach(() => useUiStore.setState({ filters: EMPTY_FILTER }));

describe("FilterBar", () => {
  it("renders the dropdown triggers + EMI toggle (no chip wall)", () => {
    render(<FilterBar units={[{ code: "59", name: "資工系" }]} classes={[{ code: "2652", name: "資工五" }]} />);
    expect(screen.getByRole("button", { name: /學院/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /系所/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /班級/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /時間/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /英文授課篩選/ })).toBeInTheDocument();
  });

  it("英文授課 三態循環（關閉→只看→排除→關閉）+ 清除全部", async () => {
    render(<FilterBar units={[]} classes={[]} />);
    const emiBtn = () => screen.getByRole("button", { name: /英文授課篩選/ });
    expect(screen.queryByRole("button", { name: "清除全部" })).not.toBeInTheDocument();

    await userEvent.click(emiBtn()); // 關閉 → 只看英文授課
    expect(useUiStore.getState().filters.emi).toBe("emi");
    expect(screen.getByText("✓ 英文授課")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "清除全部" })).toBeInTheDocument();

    await userEvent.click(emiBtn()); // 只看 → 排除英文授課
    expect(useUiStore.getState().filters.emi).toBe("non_emi");
    expect(screen.getByText("✕ 非英文授課")).toBeInTheDocument();

    await userEvent.click(emiBtn()); // 排除 → 關閉
    expect(useUiStore.getState().filters.emi).toBe("all");
    expect(screen.queryByRole("button", { name: "清除全部" })).not.toBeInTheDocument();
  });
});
