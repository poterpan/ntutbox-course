/**
 * `/browse/**` 的頁框：麵包屑 + 標題 + 內容 + 頁尾。
 *
 * **刻意不是 client component**：hub 頁的整個目的是把真實 `<a>` 放進靜態 HTML，
 * 讓不執行 JS 的爬蟲也讀得到。加上 "use client" 不會讓連結消失（Next 仍會預渲染），
 * 但會白白把資料序列化進 RSC payload、也讓人以為這裡可以用 hook。別加。
 *
 * 視覺沿用 apps/web/AGENTS.md 的 glass token 與圓角級距（面板 rounded-2xl、
 * 卡片/列 rounded-xl、pill rounded-full；顏色只走 --ink/--ink-soft/--accent）。
 */
import Link from "next/link";
import { jsonLdText } from "@/lib/hub/json-ld";

export interface Crumb {
  label: string;
  href?: string;
}

export function HubShell({
  crumbs,
  title,
  lead,
  children,
}: {
  crumbs: Crumb[];
  title: string;
  lead: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
      <nav aria-label="麵包屑" className="mb-4 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-[var(--ink-soft)]">
        {crumbs.map((c, i) => (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <span aria-hidden className="text-[var(--ink-faint)]">/</span>}
            {c.href ? (
              <Link href={c.href} className="font-medium text-[var(--accent-ink)] hover:underline">
                {c.label}
              </Link>
            ) : (
              <span aria-current="page" className="font-medium text-[var(--ink)]">{c.label}</span>
            )}
          </span>
        ))}
      </nav>

      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-[var(--ink)] sm:text-3xl">{title}</h1>
        <div className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--ink-soft)]">{lead}</div>
      </header>

      {children}

      <footer className="mt-10 border-t border-black/5 pt-5 text-xs leading-relaxed text-[var(--ink-faint)]">
        <p className="mb-2">
          <Link href="/" className="font-medium text-[var(--accent-ink)] hover:underline">
            回到排課工具
          </Link>
          <span aria-hidden className="mx-2">·</span>
          <Link href="/browse/" className="font-medium text-[var(--accent-ink)] hover:underline">
            全部系所課程總覽
          </Link>
        </p>
        <p>
          本站為獨立開發的非官方工具，與國立臺北科技大學無隸屬或合作關係。課程資料整理自校方公開的
          課程查詢系統，正式選課請以學校系統為準。
        </p>
      </footer>
    </main>
  );
}

/** 區塊標題（hub 內的分區）。 */
export function HubSection({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--ink-soft)]">{title}</h2>
      {note && <p className="mb-3 text-xs text-[var(--ink-faint)]">{note}</p>}
      {!note && <div className="mb-3" />}
      {children}
    </section>
  );
}

/** 結構化資料：hub 頁的 BreadcrumbList。爬蟲用麵包屑理解站內層級——正是本次要建立的。 */
export function HubJsonLd({ crumbs, origin }: { crumbs: Crumb[]; origin: string }) {
  const ld = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: crumbs.map((c, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: c.label,
      ...(c.href ? { item: `${origin}${c.href}` } : {}),
    })),
  };
  // 資料含爬蟲字串（單位名）→ 走 jsonLdText 轉義 "<"，見 lib/hub/json-ld.ts。
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdText(ld) }} />;
}
