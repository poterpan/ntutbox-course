import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

const SCHEDULE = {
  current: [
    { term: "115-1", from: "2026-08-01T00:00:00+08:00" },
    { term: "115-2", from: "2027-02-01T00:00:00+08:00" },
  ],
  default: [
    { term: "115-1", from: "2026-08-01T00:00:00+08:00" },
    { term: "115-2", from: "2026-11-21T17:00:00+08:00" },
  ],
};

const { getTerm } = vi.hoisted(() => ({
  getTerm: vi.fn(async (termKey: string) => ({
    termKey,
    catalog: { courses: [], term: { key: termKey }, freshness: {} },
    periods: { periods: [] }, classes: { classes: [] }, enrollment: null,
  })),
}));

vi.mock("@/lib/data", () => ({
  getDataSource: () => ({
    getManifest: vi.fn().mockResolvedValue({
      schema_version: 3, terms: { "114-2": {}, "115-1": {}, "115-2": {} }, term_schedule: SCHEDULE,
    }),
    getTerm,
  }),
}));

import { TermSwitcher } from "./TermSwitcher";
import { useUiStore } from "@/store/ui-store";
import { useTermStore } from "@/store/term-store";
import { __resetTermOptionsCache } from "@/lib/terms/use-resolved-terms";

function setNow(iso: string) {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(iso));
}

beforeEach(() => {
  __resetTermOptionsCache();
  getTerm.mockClear();
  useUiStore.setState({ selectedTerm: null });
  useTermStore.setState({ status: "idle", termKey: null, bundle: null, error: null, generation: 0 });
});
afterEach(() => vi.useRealTimers());

const select = () => screen.getByRole("combobox", { name: "選擇學期" }) as HTMLSelectElement;
const backButton = () => screen.queryByRole("button", { name: /回到本學期/ });

describe("TermSwitcher 預設學期（D21）", () => {
  it("期中撤選截止前：預設＝本學期 115-1，不顯示「回到本學期」", async () => {
    setNow("2026-09-27T12:00:00+08:00");
    render(<TermSwitcher />);
    await waitFor(() => expect(select().value).toBe("115-1"));
    expect(getTerm).toHaveBeenCalledWith("115-1");
    expect(backButton()).toBeNull();
  });

  it("截止後：預設 115-2，顯示「回到本學期（115-1）」，按下切回 115-1 並隱藏", async () => {
    setNow("2026-11-22T10:00:00+08:00");
    render(<TermSwitcher />);
    await waitFor(() => expect(select().value).toBe("115-2"));
    const btn = await screen.findByRole("button", { name: "回到本學期（115-1）" });
    expect(btn).toHaveTextContent("回到本學期（115-1）");
    fireEvent.click(btn);
    await waitFor(() => expect(select().value).toBe("115-1"));
    expect(backButton()).toBeNull();
  });

  it("手動切到其他學期 → 出現按鈕", async () => {
    setNow("2026-09-27T12:00:00+08:00");
    render(<TermSwitcher />);
    await waitFor(() => expect(select().value).toBe("115-1"));
    fireEvent.change(select(), { target: { value: "114-2" } });
    await waitFor(() => expect(select().value).toBe("114-2"));
    expect(backButton()).not.toBeNull();
  });

  it("分享連結已指定學期 → 不被預設學期覆寫", async () => {
    setNow("2026-11-22T10:00:00+08:00");
    useUiStore.setState({ selectedTerm: "114-2" });
    render(<TermSwitcher />);
    await screen.findByRole("button", { name: "回到本學期（115-1）" });
    expect(useUiStore.getState().selectedTerm).toBe("114-2");
    expect(getTerm).not.toHaveBeenCalledWith("115-2");
  });
});
