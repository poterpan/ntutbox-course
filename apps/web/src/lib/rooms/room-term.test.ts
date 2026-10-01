import { describe, expect, it } from "vitest";
import { resolveRoomTerm } from "./room-term";

const R = { url: "x", sha256: "y", size: 1 };
const NOW = new Date("2026-10-01T12:00:00+08:00");

describe("resolveRoomTerm", () => {
  it("本學期有 rooms → 本學期（即使預設學期已切到下學期）", () => {
    const manifest = {
      terms: { "115-1": { rooms: R }, "115-2": { rooms: null } },
      term_schedule: {
        current: [{ term: "115-1", from: "2026-08-01T00:00:00+08:00" }],
        default: [{ term: "115-2", from: "2026-09-01T00:00:00+08:00" }],
      },
    };
    expect(resolveRoomTerm(manifest, NOW)).toBe("115-1");
  });

  it("本學期沒有 rooms → 有 rooms 的最新學期", () => {
    const manifest = {
      terms: { "114-1": { rooms: R }, "114-2": { rooms: R }, "115-1": { rooms: null } },
      term_schedule: { current: [{ term: "115-1", from: "2026-08-01T00:00:00+08:00" }], default: [] },
    };
    expect(resolveRoomTerm(manifest, NOW)).toBe("114-2");
  });

  it("本學期不在 manifest → 有 rooms 的最新學期", () => {
    const manifest = { terms: { "114-2": { rooms: R }, "115-2": {} } };
    expect(resolveRoomTerm(manifest, NOW)).toBe("114-2");
  });

  it("舊 manifest 沒有 term_schedule → 依日期規則的本學期", () => {
    expect(resolveRoomTerm({ terms: { "115-1": { rooms: R }, "114-2": { rooms: R } } }, NOW)).toBe("115-1");
  });

  it("沒有任何學期有 rooms → null", () => {
    expect(resolveRoomTerm({ terms: { "115-1": {} } }, NOW)).toBeNull();
    expect(resolveRoomTerm(null, NOW)).toBeNull();
  });
});
