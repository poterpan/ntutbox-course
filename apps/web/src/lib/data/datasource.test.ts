import { describe, it, expect, vi, beforeEach } from "vitest";
import { HttpDataSource } from "./cdn-datasource";
import { DataLoadError } from "./datasource";

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as Response;
}

describe("HttpDataSource", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("getManifest fetches <base>/manifest.json", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ schema_version: 1, terms: {} }),
    );
    const ds = new HttpDataSource("/data/v1");
    const m = await ds.getManifest();
    expect(m.schema_version).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith("/data/v1/manifest.json", { signal: undefined });
  });

  it("getTerm bundles catalog/periods/classes and tolerates missing enrollment", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      if (u.endsWith("catalog.json")) return jsonResponse({ courses: [{ offering_id: "1" }], term: { key: "115-1" } });
      if (u.endsWith("periods.json")) return jsonResponse({ periods: [] });
      if (u.endsWith("classes.json")) return jsonResponse({ classes: [] });
      return jsonResponse(null, false, 404); // enrollment missing
    });
    const ds = new HttpDataSource("/data/v1");
    const b = await ds.getTerm("115-1");
    expect(b.termKey).toBe("115-1");
    expect(b.catalog.courses).toHaveLength(1);
    expect(b.enrollment).toBeNull();
  });

  it("throws DataLoadError on non-ok manifest", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(null, false, 500));
    const ds = new HttpDataSource("/data/v1");
    await expect(ds.getManifest()).rejects.toBeInstanceOf(DataLoadError);
  });

  it("getCourseDetail fetches course/<id>.json and returns the detail", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ term_key: "115-1", offering_id: "360748", description: { zh: "概述" }, syllabi: [] }),
    );
    const ds = new HttpDataSource("/data/v1");
    const d = await ds.getCourseDetail("115-1", "360748");
    expect(d?.offering_id).toBe("360748");
    expect(fetchMock).toHaveBeenCalledWith("/data/v1/terms/115-1/course/360748.json", { signal: undefined });
  });

  it("getCourseDetail returns null when detail is missing (404 — optional overlay)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(null, false, 404));
    const ds = new HttpDataSource("/data/v1");
    expect(await ds.getCourseDetail("115-1", "nope")).toBeNull();
  });
});
