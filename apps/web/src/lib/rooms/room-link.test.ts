import { describe, expect, it } from "vitest";
import { roomLinkHref } from "./room-link";

const INDEX = { termKey: "115-1", codes: new Set(["9", "154"]) };

describe("roomLinkHref", () => {
  it("學期相同且代碼有頁面 → 連結", () => {
    expect(roomLinkHref("154", "115-1", INDEX)).toBe("/rooms/154/");
  });
  it("學期不同 → null（其他學期的教室頁不存在）", () => {
    expect(roomLinkHref("154", "114-2", INDEX)).toBeNull();
  });
  it("代碼不在清單 → null", () => {
    expect(roomLinkHref("999", "115-1", INDEX)).toBeNull();
  });
  it("清單未就緒、沒有代碼或學期 → null", () => {
    expect(roomLinkHref("154", "115-1", null)).toBeNull();
    expect(roomLinkHref(undefined, "115-1", INDEX)).toBeNull();
    expect(roomLinkHref("154", null, INDEX)).toBeNull();
  });
});
