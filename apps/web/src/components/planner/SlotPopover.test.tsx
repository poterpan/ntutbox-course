import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SlotPopover } from "./SlotPopover";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";
import { useIdentityStore } from "@/store/identity-store";

const courses = [
  { offering_id: "A", name: { zh: "資料結構" }, credits: 3, teachers: [], meetings: [{ day: 3, periods: ["5"] }], classes: [] },
  { offering_id: "B", name: { zh: "演算法" }, credits: 3, teachers: [], meetings: [{ day: 3, periods: ["5"] }], classes: [] },
  { offering_id: "C", name: { zh: "機率論" }, credits: 3, teachers: [], meetings: [{ day: 3, periods: ["5"] }], classes: [] },
];

function setTerm() {
  useTermStore.setState({
    status: "ready", termKey: "115-1", error: null, generation: 1,
    bundle: { termKey: "115-1", catalog: { courses } as never, periods: { periods: [] } as never, classes: { classes: [] } as never, enrollment: null } as never,
  });
  useUiStore.setState({ activeSlot: { day: 3, period: "5" } });
}

beforeEach(() => useIdentityStore.setState({ matricGroup: null }));

describe("SlotPopover — manage mode (occupied slot)", () => {
  beforeEach(() => {
    setTerm();
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [{ offering_id: "A", priority: 1 }, { offering_id: "B", priority: 2 }] });
  });

  it("lists placed courses by priority and hides addable (no 加選 from timetable)", () => {
    render(<SlotPopover />);
    expect(screen.getByText("資料結構")).toBeInTheDocument();
    expect(screen.getByText("演算法")).toBeInTheDocument();
    expect(screen.queryByText("機率論")).not.toBeInTheDocument(); // addable suppressed in manage mode
  });

  it("退選 button removes a placed course", async () => {
    render(<SlotPopover />);
    await userEvent.click(screen.getByLabelText("退選 資料結構"));
    expect(useDraftStore.getState().placed.map((p) => p.offering_id)).toEqual(["B"]);
  });

  it("move-up raises priority (B above A)", async () => {
    render(<SlotPopover />);
    await userEvent.click(screen.getByLabelText("演算法 上移"));
    const p = useDraftStore.getState().placed;
    expect(p.find((x) => x.offering_id === "B")!.priority).toBeLessThan(p.find((x) => x.offering_id === "A")!.priority);
  });
});

describe("SlotPopover — add mode (empty slot)", () => {
  beforeEach(() => {
    setTerm();
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] });
  });

  it("shows search + addable courses for the slot, and ＋ places one", async () => {
    render(<SlotPopover />);
    expect(screen.getByLabelText("搜尋此時段")).toBeInTheDocument();
    expect(screen.getByText("機率論")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("排入 機率論"));
    expect(useDraftStore.getState().placed.map((p) => p.offering_id)).toEqual(["C"]);
  });
});

describe("SlotPopover — 學制過濾 (add mode)", () => {
  const matricCourses = [
    { offering_id: "G", name: { zh: "高等演算法" }, credits: 3, teachers: [], meetings: [{ day: 3, periods: ["5"] }], classes: [], raw_fields: { matric_codes: "8" } }, // 研究所
    { offering_id: "U", name: { zh: "計算機概論" }, credits: 3, teachers: [], meetings: [{ day: 3, periods: ["5"] }], classes: [], raw_fields: { matric_codes: "7" } }, // 日間部大學
  ];
  beforeEach(() => {
    useTermStore.setState({
      status: "ready", termKey: "115-1", error: null, generation: 1,
      bundle: { termKey: "115-1", catalog: { courses: matricCourses } as never, periods: { periods: [] } as never, classes: { classes: [] } as never, enrollment: null } as never,
    });
    useUiStore.setState({ activeSlot: { day: 3, period: "5" } });
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] });
    useIdentityStore.setState({ matricGroup: "grad_day" });
  });

  it("選了研究所 → 預設只顯研究所課；切換『顯示其他學制』後出現大學部課", async () => {
    render(<SlotPopover />);
    expect(screen.getByText("高等演算法")).toBeInTheDocument();
    expect(screen.queryByText("計算機概論")).not.toBeInTheDocument(); // 大學部預設隱藏
    await userEvent.click(screen.getByText(/顯示其他學制/));
    expect(screen.getByText("計算機概論")).toBeInTheDocument();       // 展開後出現
  });
});
