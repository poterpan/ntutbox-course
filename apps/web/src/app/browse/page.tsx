/**
 * `/browse/` — 課程總覽（依系所）。爬行路徑的第一站：`/` → 這裡 → 60 個系所 hub → 課程頁。
 *
 * 這是**靜態 export 產出的實體頁**（`out/browse/index.html`），連結全部寫在 HTML 裡：
 * Googlebot 與不執行 JS 的 AI 爬蟲都讀得到。首頁原本 `<a>` 數為 0（實測
 * `grep -o '<a [^>]*href' out/index.html` 無輸出）——本頁是修正的起點。
 */
import type { Metadata } from "next";
import Link from "next/link";
import { loadHubCatalog } from "@/lib/hub/build-catalog";
import { buildUnitHubs, groupUnitsByKind, type UnitHub } from "@/lib/hub/units";
import { HubShell, HubSection, HubJsonLd, type Crumb } from "@/components/hub/HubShell";
import { SITE_ORIGIN } from "@/lib/site";

export const dynamic = "force-static";

const CRUMBS: Crumb[] = [{ label: "北科盒子 排課", href: "/" }, { label: "課程總覽" }];

export async function generateMetadata(): Promise<Metadata> {
  const { termKey, courses } = await loadHubCatalog();
  const hubs = buildUnitHubs(courses);
  const total = hubs.reduce((n, h) => n + h.courseCount, 0);
  const title = `北科大課程總覽・依系所瀏覽（${termKey}）`;
  const description = `國立臺北科技大學 ${termKey} 學期 ${hubs.length} 個開課單位、共 ${total} 門課程，依系所分類瀏覽。含授課教師、學分、上課時段，可直接開啟排課工具檢查衝堂。`;
  return {
    title,
    description,
    // ⚠️ 必須覆寫：root layout 的 metadata 把全站 canonical 指向 "/"，
    // 不覆寫的話所有 hub 頁都會自我宣告「我的正式版本是首頁」→ 直接從索引消失。
    alternates: { canonical: "/browse/" },
    openGraph: { title, description, url: `${SITE_ORIGIN}/browse/`, type: "website" },
  };
}

export default async function BrowseIndexPage() {
  const { termKey, courses } = await loadHubCatalog();
  const hubs = buildUnitHubs(courses);
  const sections = groupUnitsByKind(hubs);
  const total = hubs.reduce((n, h) => n + h.courseCount, 0);

  return (
    <>
      <HubJsonLd crumbs={CRUMBS} origin={SITE_ORIGIN} />
      <HubShell
        crumbs={CRUMBS}
        title={`北科大課程總覽・依系所瀏覽（${termKey}）`}
        lead={
          <>
            <p>
              國立臺北科技大學 <strong className="font-semibold text-[var(--ink)]">{termKey}</strong> 學期共{" "}
              <strong className="font-semibold text-[var(--ink)]">{hubs.length}</strong> 個開課單位、
              <strong className="font-semibold text-[var(--ink)]">{total}</strong> 門課程。
              選一個系所看完整開課清單，或直接到{" "}
              <Link href="/" className="font-medium text-[var(--accent-ink)] hover:underline">
                排課工具
              </Link>{" "}
              搜尋、排週課表與檢查衝堂。
            </p>
          </>
        }
      >
        {sections.map((s) => (
          <HubSection key={s.kind} title={s.label} note={`${s.units.length} 個單位`}>
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {s.units.map((u) => (
                <li key={u.slug}>
                  <UnitCard unit={u} />
                </li>
              ))}
            </ul>
          </HubSection>
        ))}
      </HubShell>
    </>
  );
}

function UnitCard({ unit }: { unit: UnitHub }) {
  return (
    <Link
      href={`/browse/${unit.slug}/`}
      className="flex items-center gap-2 rounded-xl bg-white px-3 py-2.5 ring-1 ring-black/[0.07] transition-colors hover:bg-[var(--accent)]/[0.06] hover:ring-[var(--accent)]/30"
    >
      <span className="min-w-0 flex-1 truncate text-sm font-semibold text-[var(--ink)]">{unit.unitName}</span>
      <span className="shrink-0 rounded-md bg-[var(--accent)]/12 px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-[var(--accent-ink)]">
        {unit.courseCount} 門
      </span>
    </Link>
  );
}
