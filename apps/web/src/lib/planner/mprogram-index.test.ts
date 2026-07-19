import { expect, it } from "vitest";
import { buildProgramIndex, getProgramOidSet } from "./mprogram-index";

const dir = { schema_version: 2, term_key: "115-1", programs: [
  { code: "AV2", name: "面板微學程", offering_ids: ["1", "2"], courses: [], rules_text: null },
  { code: "AV3", name: "創業家精神微學程", offering_ids: ["2"], courses: [], rules_text: null },
] } as never;

it("maps offering→programs", () => {
  const idx = buildProgramIndex(dir);
  expect(idx.get("2")!.map((p) => p.code)).toEqual(["AV2", "AV3"]);
  expect(idx.get("9")).toBeUndefined();
});
it("null-safe", () => expect(buildProgramIndex(null).size).toBe(0));

it("getProgramOidSet unions offering_ids across programs (dedup)", () => {
  const set = getProgramOidSet(dir);
  expect([...set].sort()).toEqual(["1", "2"]);
  expect(set.has("2")).toBe(true);
  expect(set.has("9")).toBe(false);
});
it("getProgramOidSet null → empty set", () => expect(getProgramOidSet(null).size).toBe(0));
it("getProgramOidSet memoizes by dir reference", () => {
  expect(getProgramOidSet(dir)).toBe(getProgramOidSet(dir));
});
