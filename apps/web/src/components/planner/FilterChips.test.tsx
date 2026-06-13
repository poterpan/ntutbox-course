import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FilterChips } from "./FilterChips";
import { useUiStore } from "@/store/ui-store";
import { EMPTY_FILTER } from "@/lib/filters/types";

beforeEach(() => useUiStore.setState({ filters: EMPTY_FILTER }));

describe("FilterChips", () => {
  it("toggling 週一 chip adds weekday 1 to filters", async () => {
    render(<FilterChips units={[]} classes={[]} />);
    await userEvent.click(screen.getByRole("button", { name: "一" }));
    expect(useUiStore.getState().filters.weekdays).toContain(1);
  });
  it("toggling 英文授課 sets emiOnly", async () => {
    render(<FilterChips units={[]} classes={[]} />);
    await userEvent.click(screen.getByRole("button", { name: "英文授課" }));
    expect(useUiStore.getState().filters.emiOnly).toBe(true);
  });
});
