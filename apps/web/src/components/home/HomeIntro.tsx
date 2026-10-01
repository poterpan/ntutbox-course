/**
 * 首頁排課器下方的靜態介紹／導覽區（server component，build 期渲染進 `out/index.html`）。
 *
 * 為什麼：首頁本體是 client 端排課器，靜態 HTML 幾乎沒有文字、只連到兩頁。這一區把站的
 * 用途、四個入口、本學期數據與熱門系所 hub 連結寫進 HTML——不執行 JS 的爬蟲也讀得到。
 * 放在排課器（h-dvh）**之後**：首屏仍是排課器，往下捲才看到，不擠壓排課佈局。
 * 不用 noscript／隱藏文字：內容對使用者可見，與爬蟲看到的一致。
 *
 * **刻意不是 client component**（同 HubShell）：別加 "use client"、別用 hook。
 * 視覺沿用 apps/web/AGENTS.md 的 token 與圓角級距（面板 rounded-2xl、卡片 rounded-xl、pill rounded-full）。
 */
import Link from "next/link";
import type { HomeSummary } from "@/lib/home/home-summary";

const APP_SITE = "https://ntutbox.com/";

const CARD =
  "flex h-full flex-col gap-1 rounded-xl bg-white/80 px-4 py-3.5 ring-1 ring-black/[0.07] transition-colors hover:bg-[var(--accent)]/[0.06] hover:ring-[var(--accent)]/30 dark:bg-white/[0.06] dark:ring-white/10";

export function HomeIntro({ summary }: { summary: HomeSummary }) {
  const { termKey, courseCount, unitCount, roomTermKey, roomCount, updatedAt, topUnits } = summary;
  const entries = [
    { href: "/browse/", title: "課程總覽", desc: `依系所瀏覽 ${termKey} 學期 ${courseCount} 門課程。` },
    {
      href: "/rooms/",
      title: "教室課表",
      desc: "查每間教室整週排了哪些課，依大樓分類。",
    },
    { href: "/guide/", title: "選課指南", desc: "課表怎麼看、四種選課機制、通識與微學程怎麼選。" },
  ];

  return (
    <section
      aria-labelledby="home-intro-title"
      // pb-36：窄機的「課程庫」與分享課表 FAB 固定在右下角，捲到底時別蓋住最後一排連結。
      className="mx-auto w-full max-w-5xl px-4 pt-8 pb-36 sm:px-6 lg:pb-16"
    >
      <h2 id="home-intro-title" className="text-xl font-bold tracking-tight text-[var(--ink)] sm:text-2xl">
        北科大排課・選課規劃
      </h2>
      <div className="mt-2 max-w-3xl space-y-2 text-sm leading-relaxed text-[var(--ink-soft)]">
        {/* 中文句子別在 JSX 裡斷行：換行會被渲染成空白（「檢查， 也能」）。 */}
        <p>
          {"北科盒子 排課是給北科大學生的免登入排課工具：搜尋課程、把課排進週課表，衝堂與學分會即時檢查，也能收藏想修的課、瀏覽微學程。"}
        </p>
        <p>
          {"課程資料每日自學校公開的課程查詢系統同步；排好的課表可以分享給同學，或匯入 "}
          <a
            href={APP_SITE}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-[var(--accent-ink)] hover:underline"
          >
            北科盒子 App
          </a>
          {"。本站為非官方工具，正式選課以學校系統為準。"}
        </p>
      </div>

      <dl className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <Stat label="學期" value={termKey} />
        <Stat label="課程" value={`${courseCount} 門`} />
        <Stat label="開課單位" value={`${unitCount} 個`} />
        {roomCount != null && (
          <Stat
            label={roomTermKey && roomTermKey !== termKey ? `教室（${roomTermKey}）` : "教室"}
            value={`${roomCount} 間`}
          />
        )}
        {updatedAt && <Stat label="資料更新" value={updatedAt} small />}
      </dl>

      <ul className="mt-6 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {entries.map((e) => (
          <li key={e.href}>
            <Link href={e.href} className={CARD}>
              <span className="text-sm font-semibold text-[var(--ink)]">{e.title} →</span>
              <span className="text-xs leading-relaxed text-[var(--ink-soft)]">{e.desc}</span>
            </Link>
          </li>
        ))}
        <li>
          <a href={APP_SITE} target="_blank" rel="noopener noreferrer" className={CARD}>
            <span className="text-sm font-semibold text-[var(--ink)]">北科盒子 App ↗</span>
            <span className="text-xs leading-relaxed text-[var(--ink-soft)]">北科大的 iOS 校務 App，排好的課表可以匯入。</span>
          </a>
        </li>
      </ul>

      {topUnits.length > 0 && (
        <div className="mt-8">
          <h3 className="text-sm font-semibold text-[var(--ink)]">開課最多的系所・單位</h3>
          <ul className="mt-3 flex flex-wrap gap-2">
            {topUnits.map((u) => (
              <li key={u.slug}>
                <Link
                  href={`/browse/${u.slug}/`}
                  className="inline-flex items-center gap-1.5 rounded-full bg-white/80 px-3 py-1.5 text-xs font-medium text-[var(--ink)] ring-1 ring-black/[0.07] transition-colors hover:bg-[var(--accent)]/10 hover:text-[var(--accent-ink)] dark:bg-white/[0.06] dark:ring-white/10"
                >
                  {u.unitName}
                  <span className="tabular-nums text-[var(--ink-faint)]">{u.courseCount}</span>
                </Link>
              </li>
            ))}
            <li>
              <Link
                href="/browse/"
                className="inline-flex items-center rounded-full bg-[var(--accent)]/10 px-3 py-1.5 text-xs font-semibold text-[var(--accent-ink)] transition-colors hover:bg-[var(--accent)]/15"
              >
                全部 {unitCount} 個開課單位 →
              </Link>
            </li>
          </ul>
        </div>
      )}
    </section>
  );
}

function Stat({ label, value, small }: { label: string; value: string; small?: boolean }) {
  return (
    <div className="rounded-xl bg-white/60 px-3 py-2.5 ring-1 ring-black/[0.05] dark:bg-white/[0.04] dark:ring-white/10">
      <dt className="text-[11px] font-medium text-[var(--ink-soft)]">{label}</dt>
      <dd className={`mt-0.5 font-semibold tabular-nums text-[var(--ink)] ${small ? "text-sm" : "text-lg"}`}>{value}</dd>
    </div>
  );
}
