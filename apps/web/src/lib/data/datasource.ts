import type { Manifest, TermBundle } from "./types";

export interface DataSource {
  getManifest(signal?: AbortSignal): Promise<Manifest>;
  getTerm(termKey: string, signal?: AbortSignal): Promise<TermBundle>;
}

export class DataLoadError extends Error {
  constructor(public url: string, public cause?: unknown) {
    super(`Failed to load ${url}`);
    this.name = "DataLoadError";
  }
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
