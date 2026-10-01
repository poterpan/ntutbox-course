import { describe, expect, it } from "vitest";
import { buildRoomViews, groupRoomsByBuilding, OTHER_BUILDING, roomHref, type RawRoom } from "./rooms-view";

const NAMES = new Map([["A1T", "第一教學大樓"], ["GB", "共同科館"]]);

function room(code: string, raw: string, building?: string, extra: Partial<RawRoom> = {}): RawRoom {
  return { code, raw, gis: building ? [{ building_id: building, floor_id: "3F" }] : [], slots: [], ...extra };
}

describe("buildRoomViews", () => {
  it("對好課名／教師／課程頁連結；catalog 查不到的課號不給連結", () => {
    const [v] = buildRoomViews(
      "115-1",
      [room("9", "一教301", "A1T", { full_name: "第一教學大樓301室", capacity: 55, slots: [{ day: 1, period: "3", offering_ids: ["1", "404"] }] })],
      [{ offering_id: "1", name: { zh: "微積分" }, teachers: [{ name: "王" }, { name: "李" }] }],
      NAMES,
    );
    expect(v).toMatchObject({ code: "9", name: "第一教學大樓301室", capacity: 55, buildingName: "第一教學大樓", floorId: "3F" });
    expect(v!.slots[0]!.courses).toEqual([
      { offeringId: "1", name: "微積分", teachers: "王、李", href: "/?term=115-1&course=1" },
      { offeringId: "404", name: null, teachers: "", href: null },
    ]);
  });

  it("沒有 full_name → 顯示 raw；沒有 GIS → 其他；大樓名查不到 → building_id", () => {
    const vs = buildRoomViews("115-1", [room("1", "紡織501A"), room("2", "X101", "ZZ")], [], NAMES);
    expect(vs[0]).toMatchObject({ name: "紡織501A", buildingId: null, buildingName: OTHER_BUILDING });
    expect(vs[1]).toMatchObject({ buildingId: "ZZ", buildingName: "ZZ" });
  });
});

describe("groupRoomsByBuilding", () => {
  it("依 GIS 快照順序分組、無 GIS 歸「其他」排最後、組內自然排序", () => {
    const views = buildRoomViews(
      "115-1",
      [room("3", "共同312", "GB"), room("4", "紡織501A"), room("1", "一教310", "A1T"), room("2", "一教301", "A1T"), room("5", "一教1001", "A1T")],
      [],
      NAMES,
    );
    const groups = groupRoomsByBuilding(views, ["A1T", "GB"]);
    expect(groups.map((g) => g.buildingName)).toEqual(["第一教學大樓", "共同科館", OTHER_BUILDING]);
    expect(groups[0]!.rooms.map((r) => r.raw)).toEqual(["一教301", "一教310", "一教1001"]);
    expect(groups[2]!.buildingId).toBeNull();
  });

  it("不在快照順序內的大樓依名稱排、仍在「其他」之前", () => {
    const views = buildRoomViews("115-1", [room("1", "a", "QQ"), room("2", "b"), room("3", "c", "GB")], [], NAMES);
    expect(groupRoomsByBuilding(views, ["GB"]).map((g) => g.buildingName)).toEqual(["共同科館", "QQ", OTHER_BUILDING]);
  });
});

describe("roomHref", () => {
  it("教室頁連結帶結尾斜線（trailingSlash）", () => {
    expect(roomHref("154")).toBe("/rooms/154/");
  });
});
