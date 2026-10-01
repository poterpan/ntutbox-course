import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { RoomWeekGrid, gridDays } from "./RoomWeekGrid";
import type { RoomSlotView } from "@/lib/rooms/rooms-view";

const PERIODS = [
  { token: "1", start_hm: "08:10", end_hm: "09:00" },
  { token: "2", start_hm: "09:10", end_hm: "10:00" },
  { token: "3", start_hm: "10:10", end_hm: "11:00" },
  { token: "4", start_hm: "11:10", end_hm: "12:00" },
];

const calc = { offeringId: "1", name: "微積分", teachers: "王老師", href: "/?term=115-1&course=1" };
const phys = { offeringId: "2", name: "物理", teachers: "李老師", href: "/?term=115-1&course=2" };
const ghost = { offeringId: "9", name: null, teachers: "", href: null };

const SLOTS: RoomSlotView[] = [
  { day: 1, period: "1", courses: [calc] },
  { day: 1, period: "2", courses: [calc] },
  { day: 3, period: "3", courses: [calc, phys] },
  { day: 5, period: "4", courses: [ghost] },
];

describe("RoomWeekGrid", () => {
  it("一～六固定顯示，有週日的課才加週日", () => {
    expect(gridDays(SLOTS)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(gridDays([...SLOTS, { day: 0, period: "1", courses: [calc] }])).toEqual([1, 2, 3, 4, 5, 6, 0]);
    render(<RoomWeekGrid periods={PERIODS} slots={SLOTS} />);
    for (const d of ["週一", "週六"]) expect(screen.getByText(d)).toBeInTheDocument();
    expect(screen.queryByText("週日")).not.toBeInTheDocument();
  });

  it("相鄰節次同一門課合併成一塊；課名連到課程頁、帶教師", () => {
    render(<RoomWeekGrid periods={PERIODS} slots={SLOTS} />);
    const blocks = screen.getAllByTestId("room-slot");
    expect(blocks).toHaveLength(3); // 週一 1–2 合併、週三 3、週五 4
    expect(blocks[0]!.style.gridRow).toBe("2 / span 2");
    const link = within(blocks[0]!).getByRole("link", { name: "微積分" });
    expect(link).toHaveAttribute("href", "/?term=115-1&course=1");
    expect(within(blocks[0]!).getByText("王老師")).toBeInTheDocument();
  });

  it("同格多課全列；catalog 查不到的課顯示課號、不給連結", () => {
    render(<RoomWeekGrid periods={PERIODS} slots={SLOTS} />);
    const blocks = screen.getAllByTestId("room-slot");
    expect(within(blocks[1]!).getAllByRole("link").map((a) => a.textContent)).toEqual(["微積分", "物理"]);
    expect(within(blocks[2]!).getByText("課號 9")).toBeInTheDocument();
    expect(within(blocks[2]!).queryByRole("link")).not.toBeInTheDocument();
  });

  it("沒有時間狀態（SSR）時不標今天與現在；有的話標示", () => {
    const { rerender } = render(<RoomWeekGrid periods={PERIODS} slots={SLOTS} />);
    expect(screen.queryByText("現在")).not.toBeInTheDocument();
    expect(document.querySelector('[aria-current="date"]')).toBeNull();

    rerender(<RoomWeekGrid periods={PERIODS} slots={SLOTS} today={1} active={{ day: 1, period: "2" }} />);
    expect(document.querySelector('[aria-current="date"]')).toHaveTextContent("週一");
    const active = document.querySelector("[data-active]");
    expect(active).toHaveTextContent("微積分"); // 第 2 節落在合併的 1–2 那塊
    expect(within(active as HTMLElement).getByText("現在")).toBeInTheDocument();
  });
});
