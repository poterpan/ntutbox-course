import Link from "next/link";
import type { ReactNode } from "react";
import { GlassPanel } from "@/components/glass/GlassPanel";
import { GuideCardLink } from "@/components/guide/GuideCardLink";
import { accentButtonVariants } from "@/components/ui/accent-button";
import type { GuidePageMeta } from "@/lib/guide/pages";
import type { BreadcrumbItem } from "@/lib/guide/schema";

const NTUT_COURSE_SOURCE = "https://aps.ntut.edu.tw/course/tw/";
const NTUT_OAA = "https://oaa.ntut.edu.tw/";
const REPO = "https://github.com/poterpan/ntutbox-course";

/**
 * 指南頁（/guide/*）的共用外框：麵包屑、h1、內容面板、CTA、其他指南、揭露頁尾、JSON-LD。
 *
 * 為什麼是元件而不是 route layout：每頁的麵包屑與 JSON-LD 內容不同，layout 拿不到
 * 子頁的 metadata，用元件傳 props 最直接（也讓每頁能被 vitest 單獨 render 斷言）。
 *
 * 版面刻意**不用** h-dvh：排課器是不捲動的 app shell，指南頁是長文，要走一般文件捲動
 * （見 globals.css body 的 min-height: 100dvh + fixed 漸層）。
 */
export function GuideShell({
  breadcrumb,
  jsonLd,
  heading,
  lead,
  children,
  related,
}: {
  breadcrumb: readonly BreadcrumbItem[];
  jsonLd: readonly Record<string, unknown>[];
  heading: string;
  lead: ReactNode;
  children: ReactNode;
  /** 頁尾「其他指南」；hub 頁不需要（它本身就是清單）。 */
  related?: readonly GuidePageMeta[];
}) {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 pt-5 pb-16 sm:px-6 sm:pt-8">
      {jsonLd.map((ld, i) => (
        <script
          key={i}
          type="application/ld+json"
          // 內容全是 lib/guide/* 的靜態常數（無使用者輸入），但仍依 Next 官方 JSON-LD
          // 指南把 "<" 轉成 unicode escape，排除任何提早關閉 script 標籤的可能。
          dangerouslySetInnerHTML={{ __html: JSON.stringify(ld).replaceAll("<", "\\u003c") }}
        />
      ))}

      <nav aria-label="麵包屑" className="text-xs text-[var(--ink-faint)]">
        <ol className="flex flex-wrap items-center gap-1.5">
          {breadcrumb.map((item, i) => {
            const isLast = i === breadcrumb.length - 1;
            const path = new URL(item.url).pathname;
            return (
              <li key={item.url} className="flex items-center gap-1.5">
                {i > 0 && <span aria-hidden>/</span>}
                {isLast ? (
                  <span aria-current="page" className="text-[var(--ink-soft)]">
                    {item.name}
                  </span>
                ) : (
                  <Link href={path} className="hover:text-[var(--accent-ink)] hover:underline">
                    {item.name}
                  </Link>
                )}
              </li>
            );
          })}
        </ol>
      </nav>

      <GlassPanel className="mt-4 p-5 sm:p-8">
        <h1 className="text-xl font-bold tracking-tight text-[var(--ink)] sm:text-2xl">{heading}</h1>
        <div className="mt-3 text-sm leading-relaxed text-[var(--ink-soft)]">{lead}</div>
        <div className="mt-8">{children}</div>
      </GlassPanel>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Link href="/" className={accentButtonVariants({ size: "lg" })}>
          到排課器查課
        </Link>
        <span className="text-xs text-[var(--ink-faint)]">免登入、可直接搜尋課程並排出週課表</span>
      </div>

      {related && related.length > 0 && (
        <section className="mt-10">
          <h2 className="text-sm font-semibold text-[var(--ink)]">其他指南</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {related.map((page) => (
              <GuideCardLink key={page.slug} page={page} />
            ))}
          </div>
        </section>
      )}

      <GuideDisclosure />
    </main>
  );
}

/**
 * 每頁都出現的揭露段落。文字沿用 AboutDialog 已上線的字句（別改寫——那些字串被
 * AboutDialog.test.tsx 與 course-noscript.test.ts 釘住，站內語氣要一致）。
 */
export function GuideDisclosure() {
  return (
    <footer className="mt-12 border-t border-black/5 pt-6 text-xs leading-relaxed text-[var(--ink-faint)] dark:border-white/10">
      <p>
        <span className="font-semibold text-[var(--ink-soft)]">資料來源：</span>
        所有課程資料整理自北科大公開的
        <a
          href={NTUT_COURSE_SOURCE}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--accent-ink)] underline underline-offset-2"
        >
          官方課程查詢系統
        </a>
        ，每日自動更新。本站僅供規劃參考，正式選課請以學校選課系統送出的結果為準；
        若與學校系統有出入，一律以學校公告為準。
      </p>
      <p className="mt-2">
        <span className="font-semibold text-[var(--ink-soft)]">非官方聲明：</span>
        本站為獨立開發的非官方工具，與國立臺北科技大學無隸屬或合作關係，亦非校方委託建置。
        本頁是第三方整理的說明，不是校方規章；選課日期、學分限制與各類別應修學分等細節，
        請以
        <a
          href={NTUT_OAA}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--accent-ink)] underline underline-offset-2"
        >
          教務處公告
        </a>
        與各開課單位的規定為準。
      </p>
      <p className="mt-2">
        <span className="font-semibold text-[var(--ink-soft)]">開發與回饋：</span>
        由 PoterPan 開發與維護。內容有誤請到
        <a
          href={REPO}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--accent-ink)] underline underline-offset-2"
        >
          GitHub
        </a>
        回報。
      </p>
    </footer>
  );
}
