// 英文授課/EMI raw-value whitelist (spec §3.2). language is free text from source;
// match on substrings. Tune per-term as new values appear.
const EMI_MARKERS = ["英", "english", "emi"];

export function isEmi(language: string | null | undefined): boolean {
  if (!language) return false;
  const v = language.toLowerCase();
  return EMI_MARKERS.some((m) => v.includes(m));
}
