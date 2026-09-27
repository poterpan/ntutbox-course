import { describe, it, expect } from "vitest";
import { containingTerm, resolveTerms, termAt, type ManifestLike } from "./term-schedule";

// derive 由 115 學年度真實行事曆產出的時刻表（crawler/tests/test_term_schedule.py 同一份）。
const SCHEDULE: ManifestLike["term_schedule"] = {
  current: [
    { term: "114-2", from: "2026-02-01T00:00:00+08:00" },
    { term: "115-1", from: "2026-08-01T00:00:00+08:00" },
    { term: "115-2", from: "2027-02-01T00:00:00+08:00" },
    { term: "116-1", from: "2027-08-01T00:00:00+08:00" },
  ],
  default: [
    { term: "114-2", from: "2026-02-01T00:00:00+08:00" },
    { term: "115-1", from: "2026-08-01T00:00:00+08:00" },
    { term: "115-2", from: "2026-11-21T17:00:00+08:00" },
    { term: "116-1", from: "2027-05-08T17:00:00+08:00" },
  ],
};

const manifest = (terms: string[], schedule: ManifestLike["term_schedule"] = SCHEDULE): ManifestLike => ({
  terms: Object.fromEntries(terms.map((t) => [t, {}])),
  term_schedule: schedule,
});
const at = (iso: string) => new Date(iso);
const WITH_115_2 = ["114-2", "115-1", "115-2"];

describe("resolveTerms", () => {
  it("2026-09-27：本學期與預設都是 115-1", () => {
    expect(resolveTerms(manifest(WITH_115_2), at("2026-09-27T12:00:00+08:00"))).toEqual({ current: "115-1", default: "115-1" });
  });

  it("期中撤選截止前一分鐘仍是 115-1", () => {
    expect(resolveTerms(manifest(WITH_115_2), at("2026-11-21T16:59:00+08:00")).default).toBe("115-1");
  });

  it("期中撤選截止（11/21 17:00）起預設 115-2，本學期仍是 115-1", () => {
    expect(resolveTerms(manifest(WITH_115_2), at("2026-11-21T17:00:00+08:00"))).toEqual({ current: "115-1", default: "115-2" });
  });

  it("下學期還沒有 catalog → 預設退回本學期", () => {
    expect(resolveTerms(manifest(["114-2", "115-1"]), at("2026-11-22T10:00:00+08:00")).default).toBe("115-1");
  });

  it("2027-02-01：本學期與預設都是 115-2", () => {
    expect(resolveTerms(manifest(WITH_115_2), at("2027-02-01T00:00:00+08:00"))).toEqual({ current: "115-2", default: "115-2" });
  });

  it("2027-05-08 17:00 預設 116-1；116-1 沒有 catalog → 退回本學期 115-2", () => {
    const now = at("2027-05-08T17:00:00+08:00");
    expect(resolveTerms(manifest([...WITH_115_2, "116-1"]), now)).toEqual({ current: "115-2", default: "116-1" });
    expect(resolveTerms(manifest(WITH_115_2), now)).toEqual({ current: "115-2", default: "115-2" });
  });

  it("本學期也沒有 catalog → 預設退回 manifest 最新學期、current 為 null", () => {
    expect(resolveTerms(manifest(["114-1", "114-2"]), at("2026-09-27T12:00:00+08:00"))).toEqual({ current: null, default: "114-2" });
  });

  it("舊 manifest 沒有 term_schedule → 預設＝最新學期（D21 之前的行為），本學期照日期算", () => {
    expect(resolveTerms(manifest(["114-2", "115-1"], null), at("2026-09-27T12:00:00+08:00"))).toEqual({ current: "115-1", default: "115-1" });
    expect(resolveTerms({ terms: manifest(WITH_115_2).terms }, at("2026-09-27T12:00:00+08:00"))).toEqual({ current: "115-1", default: "115-2" });
  });

  it("manifest 空 / 缺 → default null", () => {
    expect(resolveTerms(null, at("2026-09-27T12:00:00+08:00"))).toEqual({ current: null, default: null });
    expect(resolveTerms({ terms: {} }, at("2026-09-27T12:00:00+08:00")).default).toBeNull();
  });
});

describe("containingTerm（台北時間）", () => {
  it.each([
    ["2026-07-31T15:59:59Z", "114-2"], // 台北 7/31 23:59:59
    ["2026-07-31T16:00:00Z", "115-1"], // 台北 8/1 00:00
    ["2027-01-31T12:00:00+08:00", "115-1"],
    ["2027-02-01T00:00:00+08:00", "115-2"],
  ])("%s → %s", (iso, term) => {
    expect(containingTerm(new Date(iso))).toBe(term);
  });
});

describe("termAt", () => {
  it("早於所有項目 → null；壞掉的日期略過", () => {
    expect(termAt(SCHEDULE!.current, at("2020-01-01T00:00:00+08:00"))).toBeNull();
    expect(termAt([{ term: "115-1", from: "bogus" }], at("2026-09-27T00:00:00+08:00"))).toBeNull();
  });
});
