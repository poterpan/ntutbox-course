import { describe, expect, it } from "vitest";
import { occupancyAt, slotAt, slotNow, statusLine, type MapRoomInput } from "./rooms-occupancy";

// 115-1 periods.json 的節次表（同 room-now.test.ts）
const PERIODS = {
  timezone: "Asia/Taipei",
  periods: [
    ["1", "08:10", "09:00"], ["2", "09:10", "10:00"], ["3", "10:10", "11:00"], ["4", "11:10", "12:00"],
    ["N", "12:10", "13:00"], ["5", "13:10", "14:00"], ["6", "14:10", "15:00"], ["7", "15:10", "16:00"],
    ["8", "16:10", "17:00"], ["9", "17:10", "18:00"], ["A", "18:30", "19:20"], ["B", "19:20", "20:10"],
    ["C", "20:20", "21:10"], ["D", "21:10", "22:00"],
  ].map(([token, start_hm, end_hm], order) => ({ token: token!, order, start_hm: start_hm!, end_hm: end_hm! })),
};
const taipei = (date: string, hm: string) => new Date(`${date}T${hm}:00+08:00`);
const MON = "2026-09-28";

function room(code: string, slotKeys: string[], over: Partial<MapRoomInput> = {}): MapRoomInput {
  return {
    code,
    raw: `三教${code}`,
    name: `第三教學大樓${code}室`,
    capacity: 60,
    gis: [{ buildingId: "A3T", floorId: "3F", classNumber: code }],
    gisMatch: "rule",
    slotKeys,
    ...over,
  };
}

describe("slotNow", () => {
  it("節內 → 該節，inSession", () => {
    expect(slotNow(taipei(MON, "10:30"), PERIODS)).toMatchObject({ day: 1, period: "3", inSession: true, nextDay: false });
  });
  it("節間 → 下一節", () => {
    expect(slotNow(taipei(MON, "10:05"), PERIODS)).toMatchObject({ day: 1, period: "3", inSession: false });
  });
  it("第一節之前 → 今天第一節", () => {
    expect(slotNow(taipei(MON, "07:00"), PERIODS)).toMatchObject({ day: 1, period: "1", nextDay: false });
  });
  it("最後一節之後 → 明天第一節，以第一節開始時刻判斷", () => {
    expect(slotNow(taipei(MON, "23:00"), PERIODS)).toMatchObject({ day: 2, period: "1", nextDay: true, refMinute: 8 * 60 + 10 });
  });
  it("週六深夜 → 週日", () => {
    expect(slotNow(taipei("2026-10-03", "23:30"), PERIODS)).toMatchObject({ day: 0, nextDay: true });
  });
});

describe("occupancyAt", () => {
  const at3 = slotAt(1, "3", PERIODS)!;

  it("有課：連堂算到最後一節結束", () => {
    const { map } = occupancyAt([room("301", ["1-3", "1-4", "1-5"])], PERIODS, at3);
    expect(map.get("A3T/3F/301")).toMatchObject({ status: "busy", busyUntil: "12:00" });
  });

  it("沒排課：下一堂在 60 分鐘內 → 快有課；更晚 → 沒排課到幾點", () => {
    const { map } = occupancyAt(
      [room("302", ["1-4"]), room("303", ["1-6"]), room("304", ["2-3"])],
      PERIODS,
      at3,
    );
    expect(map.get("A3T/3F/302")).toMatchObject({ status: "soon", freeUntil: "11:10" });
    expect(map.get("A3T/3F/303")).toMatchObject({ status: "free", freeUntil: "14:10" });
    expect(map.get("A3T/3F/304")).toMatchObject({ status: "free", freeUntil: null }); // 別天的課不算
  });

  it("現在的「快有課」以現在時刻判斷，選的節次以節次開始判斷", () => {
    const rooms = [room("305", ["1-A"])]; // 第 A 節 18:30
    const now = slotNow(taipei(MON, "17:50"), PERIODS)!; // 第 9 節內：距 18:30 還 40 分
    expect(occupancyAt(rooms, PERIODS, now).map.get("A3T/3F/305")).toMatchObject({ status: "soon", freeUntil: "18:30" });
    const picked = slotAt(1, "9", PERIODS)!; // 從 17:10 算是 80 分
    expect(occupancyAt(rooms, PERIODS, picked).map.get("A3T/3F/305")).toMatchObject({ status: "free", freeUntil: "18:30" });
  });

  it("floor_only 用 ?代碼 鍵；building_only／none 進 unplaced；byCode 全部都有", () => {
    const { map, byCode, unplaced } = occupancyAt(
      [
        room("X1", [], { gisMatch: "floor_only", gis: [{ buildingId: "CE", floorId: "1F", classNumber: null }] }),
        room("X2", [], { gisMatch: "building_only", gis: [{ buildingId: "HR", floorId: null, classNumber: null }] }),
        room("X3", [], { gisMatch: "none", gis: [] }),
      ],
      PERIODS,
      at3,
    );
    expect([...map.keys()]).toEqual(["CE/1F/?X1"]);
    expect(unplaced).toEqual(["X2", "X3"]);
    expect(byCode.size).toBe(3);
  });

  it("一間教室對到多個空間：每個空間都上色", () => {
    const { map } = occupancyAt(
      [room("401", [], { gis: [{ buildingId: "CB", floorId: "4F", classNumber: "401" }, { buildingId: "CB", floorId: "4F", classNumber: "401-1" }] })],
      PERIODS,
      at3,
    );
    expect([...map.keys()].sort()).toEqual(["CB/4F/401", "CB/4F/401-1"]);
  });
});

describe("statusLine", () => {
  it("依課表的說法", () => {
    expect(statusLine({ status: "busy", busyUntil: "12:00", freeUntil: null })).toBe("有課到 12:00");
    expect(statusLine({ status: "soon", freeUntil: "11:10", busyUntil: null })).toBe("11:10 有課");
    expect(statusLine({ status: "free", freeUntil: null, busyUntil: null })).toBe("這天沒有再排課");
  });
});
