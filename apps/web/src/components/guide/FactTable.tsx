import type { ReactNode } from "react";

/**
 * 指南頁的資料表（節次時間、修別符號、選課機制…）。
 *
 * 為什麼要一個元件：長句對照表在手機上一定會超寬，逐頁手刻 overflow 容器歷史上會漂移。
 * 這裡固定「需要時由表格自己在 rounded-xl 容器內橫向捲動」，頁面本體永遠不會出現橫向捲軸。
 * 圓角走 rounded-xl（卡片級距，見 apps/web/AGENTS.md 圓角級距表）。
 */
export function FactTable({
  head,
  rows,
  caption,
  layout = "auto",
}: {
  head: readonly string[];
  rows: readonly (readonly ReactNode[])[];
  /** 給螢幕閱讀器與列印用的表格說明；視覺上隱藏。 */
  caption?: string;
  /**
   * `auto`：窄表（2–3 個短欄），min-width 壓在手機視寬內 → 不會橫捲。
   * `wide`：欄位是長句的對照表，硬塞進手機寬度會擠成一條條的字，寧可橫捲。
   */
  layout?: "auto" | "wide";
}) {
  return (
    <div className="thin-scroll overflow-x-auto rounded-xl border border-black/5 bg-white/45 dark:border-white/10 dark:bg-white/5">
      <table
        className={
          layout === "wide"
            ? "w-full min-w-[34rem] border-collapse text-sm"
            : "w-full min-w-[18rem] border-collapse text-sm"
        }
      >
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            {head.map((h) => (
              <th
                key={h}
                scope="col"
                className="border-b border-black/5 px-3 py-2 text-left text-xs font-semibold whitespace-nowrap text-[var(--ink-soft)] dark:border-white/10"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-black/5 last:border-0 dark:border-white/10">
              {row.map((cell, j) => (
                <td
                  key={j}
                  className={
                    j === 0
                      ? "px-3 py-2 align-top font-semibold whitespace-nowrap text-[var(--ink)]"
                      : "px-3 py-2 align-top text-[var(--ink-soft)]"
                  }
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
