import type { Manifest, TermBundle, CourseDetail } from "./types";

export interface DataSource {
  getManifest(signal?: AbortSignal): Promise<Manifest>;
  getTerm(termKey: string, signal?: AbortSignal): Promise<TermBundle>;
  /** Heavy per-course detail (description + syllabi), fetched on demand.
   *  Returns null if not available (e.g. 404 — details are an optional overlay). */
  getCourseDetail(termKey: string, offeringId: string, signal?: AbortSignal): Promise<CourseDetail | null>;
}

export class DataLoadError extends Error {
  constructor(public url: string, public cause?: unknown) {
    super(`Failed to load ${url}`);
    this.name = "DataLoadError";
  }
}

/** Type-safe AbortError detection (no unsound cast). */
export function isAbortError(cause: unknown): boolean {
  return (
    typeof cause === "object" && cause !== null && "name" in cause &&
    (cause as { name: unknown }).name === "AbortError"
  );
}

// Shared fetch+parse helper (no sha256 verification in M1, per spec §2.1).
export async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, { signal });
  } catch (e) {
    throw new DataLoadError(url, e);
  }
  if (!res.ok) throw new DataLoadError(url, `HTTP ${res.status}`);
  try {
    return (await res.json()) as T;
  } catch (e) {
    throw new DataLoadError(url, e);
  }
}
