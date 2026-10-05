import { describe, expect, it, vi } from "vitest";
import { buildingsFromRooms } from "./build-rooms";

describe("buildingsFromRooms（rooms.json `buildings`，D28）", () => {
  it("名稱取 label、順序依 order（沒有 order 的排後面、再依代碼）", () => {
    const { names, order } = buildingsFromRooms(
      {
        buildings: [
          { building_id: "RB", label: "紅樓" },
          { building_id: "CB", label: "綜合科館", order: 90 },
          { building_id: "HR", label: "宏裕科研大樓", order: 70 },
          { building_id: "AA", label: "", order: null },
          { building_id: "A1T", label: "第一教學大樓", order: 10 },
        ],
      },
      "115-1",
    );
    expect(order).toEqual(["A1T", "HR", "CB", "AA", "RB"]);
    expect(names.get("HR")).toBe("宏裕科研大樓");
    expect(names.get("AA")).toBe("AA"); // label 空 → building_id
  });

  it("舊檔沒有 buildings → 空（分組退回依代碼）並告警", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { names, order } = buildingsFromRooms({}, "114-2");
    expect(order).toEqual([]);
    expect(names.size).toBe(0);
    expect(warn).toHaveBeenCalledOnce();
    warn.mockRestore();
  });

  it("舊檔沒有 buildings → 退回凍結快照的官方名稱與順序", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { names, order } = buildingsFromRooms({}, "115-1", [
      { building_id: "A1T", name: "第一教學大樓" },
      { building_id: "HR", name: "宏裕科技研究大樓" },
    ]);
    expect(order).toEqual(["A1T", "HR"]);
    expect(names.get("HR")).toBe("宏裕科技研究大樓");
    warn.mockRestore();
  });
});
