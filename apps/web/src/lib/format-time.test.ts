import { describe, expect, it } from "vitest";
import { formatTaipeiDateTime } from "./format-time";

describe("formatTaipeiDateTime", () => {
  it("固定換成台北時間、24 小時制", () => {
    expect(formatTaipeiDateTime("2026-10-01T07:24:45+08:00")).toBe("2026-10-01 07:24");
    expect(formatTaipeiDateTime("2026-09-30T23:30:00Z")).toBe("2026-10-01 07:30");
    expect(formatTaipeiDateTime("2026-10-01T00:05:00+08:00")).toBe("2026-10-01 00:05");
  });

  it("沒有值或解析失敗回 null（不捏造時間）", () => {
    expect(formatTaipeiDateTime(null)).toBeNull();
    expect(formatTaipeiDateTime(undefined)).toBeNull();
    expect(formatTaipeiDateTime("")).toBeNull();
    expect(formatTaipeiDateTime("not-a-date")).toBeNull();
  });
});
