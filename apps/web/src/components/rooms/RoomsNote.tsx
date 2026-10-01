/**
 * 教室頁的誠實語意說明（D23／D25）：slot＝「有排課」，不是「被占用」。server component。
 */
function formatCheckedAt(iso: string | null): string | null {
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

export function RoomsNote({ termKey, checkedAt }: { termKey: string; checkedAt: string | null }) {
  const checked = formatCheckedAt(checkedAt);
  return (
    <aside className="mt-8 rounded-xl bg-white/60 px-4 py-3 text-xs leading-relaxed text-[var(--ink-soft)] ring-1 ring-black/[0.07] dark:bg-white/[0.05] dark:ring-white/10">
      <p>
        依學校 {termKey} 學期教室課表推算；<strong className="font-semibold text-[var(--ink)]">有排課不代表教室正在使用，沒排課也不保證空著</strong>
        （借用、調課、考試、停課不會出現在課表上）。
      </p>
      {checked && <p className="mt-1">資料檢查時間：{checked}（台北時間）</p>}
    </aside>
  );
}
