/**
 * 教室頁的誠實語意說明（D23／D25）：slot＝「有排課」，不是「被占用」。server component。
 */
import { formatTaipeiDateTime } from "@/lib/format-time";

export function RoomsNote({ termKey, checkedAt }: { termKey: string; checkedAt: string | null }) {
  const checked = formatTaipeiDateTime(checkedAt);
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
