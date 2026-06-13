import type { SearchDoc } from "./build-index";
import { normalize, bigrams } from "./normalize";

export interface SearchOptions {
  limit?: number;       // default 200 (spec §3.1)
  signal?: AbortSignal; // cheap honor; search is sync sub-ms
}

interface Scored { doc: SearchDoc; score: number; }

export function search(docs: SearchDoc[], rawQuery: string, opts: SearchOptions = {}): SearchDoc[] {
  const limit = opts.limit ?? 200;
  if (opts.signal?.aborted) return [];
  const q = normalize(rawQuery);
  if (!q) return docs.slice(0, limit);

  const qbg = bigrams(q);
  const scored: Scored[] = [];
  for (const doc of docs) {
    let score = 0;
    if (doc.codeKeys.includes(q) || doc.offeringId === q) score = 1000; // exact code/id
    else if (doc.codeKeys.some((k) => k.startsWith(q)) || doc.offeringId.startsWith(q)) score = 500; // prefix
    else if (doc.nameKey === q) score = 400;                          // name exact
    else if (doc.nameKey.startsWith(q)) score = 300;                  // name prefix
    else {
      // contiguous substring is the strongest fallback signal
      if (doc.blob.includes(q)) {
        score = 200;
      } else {
        // bigram overlap (CJK) — only full overlap (all query bigrams present, but scattered)
        // ranks below a contiguous substring. Avoids false positives:
        // "李老師" shares only "老師" with "王老師" (partial) → no match.
        let shared = 0;
        for (const b of qbg) if (doc.bigrams.has(b)) shared++;
        if (qbg.size > 0 && shared === qbg.size) score = 150;
      }
    }
    if (score > 0) scored.push({ doc, score });
  }
  scored.sort((a, b) =>
    b.score - a.score || a.doc.offeringId.localeCompare(b.doc.offeringId), // tie-break: offering_id asc
  );
  return scored.slice(0, limit).map((s) => s.doc);
}
