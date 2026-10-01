/** ISO 時間 → 「YYYY-MM-DD HH:mm」（台北時間）。無值或解析失敗回 null（呈現端自己決定要不要顯示）。
 * build 期（server component）與 client 都能用；固定 Asia/Taipei，不吃 build 機器的時區。 */
export function formatTaipeiDateTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return null;
  const parts = new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(t);
  const get = (k: string) => parts.find((p) => p.type === k)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}`;
}
