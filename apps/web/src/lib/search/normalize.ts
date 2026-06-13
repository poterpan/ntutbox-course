/** NFKC (full-width→half-width), lowercase, strip all whitespace. */
export function normalize(s: string | null | undefined): string {
  if (!s) return "";
  return s.normalize("NFKC").toLowerCase().replace(/\s+/g, "");
}

/** Overlapping 2-grams of a normalized string; single-char → the unigram. */
export function bigrams(s: string): Set<string> {
  const out = new Set<string>();
  if (!s) return out;
  if (s.length === 1) { out.add(s); return out; }
  for (let i = 0; i < s.length - 1; i++) out.add(s.slice(i, i + 2));
  return out;
}
