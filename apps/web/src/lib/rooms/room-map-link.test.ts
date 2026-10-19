import { describe, expect, it } from "vitest";
import { roomMapHref } from "./room-map-link";

describe("roomMapHref", () => {
  it("對到門牌 → 進到那棟那層、選好那間", () => {
    expect(roomMapHref([{ buildingId: "A1T", floorId: "3F", classNumber: "301" }])).toBe(
      "https://map.ntutbox.com/?b=A1T&f=3F&r=301",
    );
  });
  it("多個空間：取第一個對到門牌的", () => {
    expect(
      roomMapHref([
        { buildingId: "A6T", floorId: "2F", classNumber: null },
        { buildingId: "A6T", floorId: "2F", classNumber: "205" },
      ]),
    ).toBe("https://map.ntutbox.com/?b=A6T&f=2F&r=205");
  });
  it("只知道樓層 → 開到那層；只知道大樓 → 選建築", () => {
    expect(roomMapHref([{ buildingId: "A6T", floorId: "2F", classNumber: null }])).toBe("https://map.ntutbox.com/?b=A6T&f=2F");
    expect(roomMapHref([{ buildingId: "CB", floorId: null, classNumber: null }])).toBe("https://map.ntutbox.com/?b=CB");
  });
  it("門牌含特殊字元要編碼", () => {
    expect(roomMapHref([{ buildingId: "CB", floorId: "B1", classNumber: "501#2" }])).toBe(
      "https://map.ntutbox.com/?b=CB&f=B1&r=501%232",
    );
  });
  it("沒有 GIS → null", () => {
    expect(roomMapHref([])).toBeNull();
  });
});
