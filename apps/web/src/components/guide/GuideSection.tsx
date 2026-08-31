import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

/**
 * 指南頁的段落標題 + 內容。文字階層一律走 --ink / --ink-soft（見 apps/web/AGENTS.md：
 * 禁止用 raw Tailwind 色當次要文字）。
 *
 * `id` 讓段落可被錨點連結（頁內目錄、外部引用）。
 */
export function GuideSection({
  id,
  title,
  children,
  className,
}: {
  id: string;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={cn("mt-10 scroll-mt-6 first:mt-0", className)}>
      <h2 className="text-lg font-bold tracking-tight text-[var(--ink)]">{title}</h2>
      <div className="mt-3 space-y-3 text-sm leading-relaxed text-[var(--ink-soft)]">{children}</div>
    </section>
  );
}

/**
 * 提醒方塊。`caution` 用在「這裡可能會誤解／本站不保證」這類必須顯眼的話，
 * `info` 用在補充說明。兩者都只用 accent token，不引入新顏色。
 */
export function GuideNote({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "caution";
  title?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border p-4 text-sm leading-relaxed",
        tone === "caution"
          ? "border-[var(--accent)]/30 bg-[var(--accent)]/10 text-[var(--accent-ink)]"
          : "border-black/5 bg-white/45 text-[var(--ink-soft)] dark:border-white/10 dark:bg-white/5",
      )}
    >
      {title && (
        <p
          className={cn(
            "mb-1 font-semibold",
            tone === "caution" ? "text-[var(--accent-ink)]" : "text-[var(--ink)]",
          )}
        >
          {title}
        </p>
      )}
      {children}
    </div>
  );
}

/** 條列。指南頁的清單很多，統一縮排與行距，避免每頁各寫一套 class。 */
export function GuideList({ items }: { items: readonly ReactNode[] }) {
  return (
    <ul className="ml-4 list-disc space-y-1.5">
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  );
}
