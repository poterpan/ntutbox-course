import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { CreditSummary } from "./CreditSummary";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";

const courses = [
  { offering_id: "A", name: { zh: "資料結構" }, credits: 3, meetings: [{ day: 3, periods: ["5"] }], classes: [], teachers: [] },
  { offering_id: "B", name: { zh: "演算法" }, credits: 3, meetings: [{ day: 3, periods: ["5"] }], classes: [], teachers: [] },
  { offering_id: "C", name: { zh: "體育" }, credits: 1, meetings: [{ day: 5, periods: ["1"] }], classes: [], teachers: [] },
];

beforeEach(() => {
  useTermStore.setState({ status: "ready", termKey: "115-1", error: null, generation: 1,
    bundle: { termKey: "115-1", catalog: { courses } as never, periods: { periods: [] } as never, classes: { classes: [] } as never, enrollment: null } as never });
  useDraftStore.setState({ termKey: "115-1", favorites: [],
    placed: [{ offering_id: "A", priority: 1 }, { offering_id: "B", priority: 2 }, { offering_id: "C", priority: 3 }] });
});

describe("CreditSummary", () => {
  it("shows first-choice credits (A over B = 3, + C = 4) and conflict count 1", () => {
    render(<CreditSummary />);
    // Text split across <span>/<b> — credit value in bold child node
    // Use getAllByText with custom matcher and check at least one match exists
    const creditEls = screen.getAllByText((_content, el) => !!el && /第一志願/.test(el.textContent ?? "") && /4/.test(el.textContent ?? ""));
    expect(creditEls.length).toBeGreaterThan(0);
    expect(screen.getByText(/衝堂.*1/)).toBeInTheDocument();
  });
});
