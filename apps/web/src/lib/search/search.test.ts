import { describe, it, expect } from "vitest";
import { search } from "./search";
import type { SearchDoc } from "./build-index";

function doc(offeringId: string, name: string, code: string, blobExtra = ""): SearchDoc {
  const blob = (name + code + blobExtra).normalize("NFKC").toLowerCase().replace(/\s+/g, "");
  const bg = new Set<string>();
  for (let i = 0; i < blob.length - 1; i++) bg.add(blob.slice(i, i + 2));
  return { offeringId, codeKeys: [code.toLowerCase()], nameKey: name.toLowerCase(), blob, bigrams: bg };
}

const docs: SearchDoc[] = [
  doc("360712", "資料結構", "2b05003", "王老師"),
  doc("360820", "演算法", "2b05004", "李老師"),
  doc("360905", "資料庫系統", "2b05010", "陳老師"),
];

describe("search", () => {
  it("exact offering_id ranks first", () => {
    expect(search(docs, "360712")[0].offeringId).toBe("360712");
  });
  it("name substring/bigram finds courses ('資料' → 資料結構 & 資料庫系統)", () => {
    const ids = search(docs, "資料").map((d) => d.offeringId);
    expect(ids).toContain("360712");
    expect(ids).toContain("360905");
    expect(ids).not.toContain("360820");
  });
  it("teacher name is searchable (search anything)", () => {
    expect(search(docs, "李老師").map((d) => d.offeringId)).toEqual(["360820"]);
  });
  it("empty query returns all (capped)", () => {
    expect(search(docs, "  ")).toHaveLength(3);
  });
  it("respects result cap", () => {
    expect(search(docs, "", { limit: 2 })).toHaveLength(2);
  });
});
