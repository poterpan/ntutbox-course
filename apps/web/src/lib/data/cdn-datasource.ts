import type { DataSource } from "./datasource";
import { fetchJson, DataLoadError, isAbortError } from "./datasource";
import type { Manifest, TermBundle, TermCatalog, PeriodTable, ClassDirectory, EnrollmentLatest } from "./types";

export class HttpDataSource implements DataSource {
  constructor(private base: string) {}

  async getManifest(signal?: AbortSignal): Promise<Manifest> {
    return fetchJson<Manifest>(`${this.base}/manifest.json`, signal);
  }

  async getTerm(termKey: string, signal?: AbortSignal): Promise<TermBundle> {
    const dir = `${this.base}/terms/${termKey}`;
    const [catalog, periods, classes] = await Promise.all([
      fetchJson<TermCatalog>(`${dir}/catalog.json`, signal),
      fetchJson<PeriodTable>(`${dir}/periods.json`, signal),
      fetchJson<ClassDirectory>(`${dir}/classes.json`, signal),
    ]);
    // enrollment overlay is optional (spec §5.4): tolerate missing.
    let enrollment: EnrollmentLatest | null = null;
    try {
      enrollment = await fetchJson<EnrollmentLatest>(`${dir}/enrollment.json`, signal);
    } catch (e) {
      if (e instanceof DataLoadError && isAbortError(e.cause)) throw e;
      enrollment = null;
    }
    return { termKey, catalog, periods, classes, enrollment };
  }
}
