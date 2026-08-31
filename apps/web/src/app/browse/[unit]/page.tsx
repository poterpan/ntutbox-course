/**
 * `/browse/<unit>/` — 單一開課單位的完整開課清單（每個 unit_code 一頁）。
 *
 * 爬行路徑的關鍵一段：這裡是課程頁**唯一的靜態內部連結來源**。
 * 每一列都是真的 `<a href="/?term=…&course=…">`，寫在靜態 HTML 裡；
 * 60 個單位頁合起來覆蓋當學期全部非佔位課程 → sitemap 裡的課程 URL 從
 * 「0 條內部連結」變成「至少 1 條、距首頁 2 click」。
 *
 * URL 刻意不帶 term（`/browse/36/` 而非 `/browse/115-1/36/`）：hub 的 canonical
 * 語意是「這個系所的課」，跟著最新學期走，URL 才穩定、不會每學期產生一批新孤島。
 * 顯示的學期寫在頁面內容裡。
 */
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { loadHubCatalog } from "@/lib/hub/build-catalog";
import { buildUnitHubs, siblingUnits, type HubCourseRow, type UnitHub } from "@/lib/hub/units";
import { HubShell, HubSection, HubJsonLd, type Crumb } from "@/components/hub/HubShell";
import { courseHref } from "@/lib/share/course-link";
import { SITE_ORIGIN } from "@/lib/site";

export const dynamic = "force-static";
// static export 不允許 dynamicParams: true（見 next/dist/docs static-exports.md
// 「Unsupported Features」）。未在 generateStaticParams 的 slug → 404。
export const dynamicParams = false;

export async function generateStaticParams() {
  const { courses } = await loadHubCatalog();
  return buildUnitHubs(courses).map((h) => ({ unit: h.slug }));
}

async function resolveUnit(slug: string): Promise<{ termKey: string; hubs: UnitHub[]; hub: UnitHub }> {
  const { termKey, courses } = await loadHubCatalog();
  const hubs = buildUnitHubs(courses);
  const hub = hubs.find((h) => h.slug === slug);
  if (!hub) notFound();
  return { termKey, hubs, hub };
}

/** 每頁獨有的敘述（避免 60 頁描述雷同被判重複內容）：教師數 / 學分區間都由該單位的課推導。 */
function unitStats(hub: UnitHub) {
  const teachers = new Set<string>();
  let withTime = 0;
  const credits: number[] = [];
  for (const c of hub.courses) {
    for (const t of c.teachers.split("、")) if (t.trim()) teachers.add(t.trim());
    if (c.schedule) withTime += 1;
    const n = Number(c.credits);
    if (Number.isFinite(n)) credits.push(n);
  }
  return {
    teacherCount: teachers.size,
    withTime,
    minCredit: credits.length ? Math.min(...credits) : null,
    maxCredit: credits.length ? Math.max(...credits) : null,
  };
}

export async function generateMetadata({ params }: { params: Promise<{ unit: string }> }): Promise<Metadata> {
  const { unit } = await params;
  const { termKey, hub } = await resolveUnit(unit);
  const s = unitStats(hub);
  const title = `${hub.unitName} 課程一覽（${termKey}）`;
  const description = `國立臺北科技大學 ${hub.unitName} ${termKey} 學期共 ${hub.courseCount} 門課程、${s.teacherCount} 位授課教師。列出課號、學分、修別、上課時段，點課程可直接排入週課表並檢查衝堂。`;
  return {
    title,
    description,
    // 同 /browse/：一定要覆寫 root layout 的 canonical: "/"。
    alternates: { canonical: `/browse/${hub.slug}/` },
    openGraph: { title, description, url: `${SITE_ORIGIN}/browse/${hub.slug}/`, type: "website" },
  };
}

export default async function UnitHubPage({ params }: { params: Promise<{ unit: string }> }) {
  const { unit } = await params;
  const { termKey, hubs, hub } = await resolveUnit(unit);
  const s = unitStats(hub);
  const siblings = siblingUnits(hubs, hub.slug);
  const crumbs: Crumb[] = [
    { label: "北科盒子 排課", href: "/" },
    { label: "課程總覽", href: "/browse/" },
    { label: hub.unitName },
  ];

  return (
    <>
      <HubJsonLd crumbs={crumbs} origin={SITE_ORIGIN} />
      <HubShell
        crumbs={crumbs}
        title={`${hub.unitName} 課程一覽（${termKey}）`}
        lead={
          <p>
            {hub.unitName}（單位代碼 {hub.unitCode}）在 {termKey} 學期共開設{" "}
            <strong className="font-semibold text-[var(--ink)]">{hub.courseCount}</strong> 門課程，
            {s.teacherCount > 0 && <>由 {s.teacherCount} 位教師授課，</>}
            {s.minCredit != null && s.maxCredit != null && (
              <>
                學分 {s.minCredit === s.maxCredit ? s.minCredit : `${s.minCredit}–${s.maxCredit}`}，
              </>
            )}
            其中 {s.withTime} 門有固定上課時段。點任一門課會在排課工具開啟該課詳情（課綱、教室、已選人數），
            並可直接排入週課表檢查衝堂。
          </p>
        }
      >
        <HubSection title={`${termKey} 開課清單`} note={`${hub.courseCount} 門・依課號排序`}>
          <ul className="flex flex-col gap-1.5">
            {hub.courses.map((c) => (
              <li key={c.offeringId}>
                <CourseRow termKey={termKey} course={c} />
              </li>
            ))}
          </ul>
        </HubSection>

        {siblings.length > 0 && (
          <HubSection title="其他單位" note="同類型的其他開課單位">
            <ul className="flex flex-wrap gap-1.5">
              {siblings.map((u) => (
                <li key={u.slug}>
                  <Link
                    href={`/browse/${u.slug}/`}
                    className="inline-flex items-center gap-1.5 rounded-full bg-[var(--accent)]/10 px-3 py-1.5 text-xs font-semibold text-[var(--accent-ink)] transition-colors hover:bg-[var(--accent)]/15"
                  >
                    {u.unitName}
                    <span className="tabular-nums opacity-70">{u.courseCount}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </HubSection>
        )}
      </HubShell>
    </>
  );
}

function CourseRow({ termKey, course }: { termKey: string; course: HubCourseRow }) {
  return (
    <Link
      href={courseHref({ termKey, offeringId: course.offeringId })}
      className="flex flex-col gap-0.5 rounded-xl bg-white px-3 py-2.5 ring-1 ring-black/[0.07] transition-colors hover:bg-[var(--accent)]/[0.06] hover:ring-[var(--accent)]/30"
    >
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="text-sm font-semibold text-[var(--ink)]">{course.name}</span>
        {course.credits && (
          <span className="shrink-0 rounded-md bg-[var(--accent)]/12 px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-[var(--accent-ink)]">
            {course.credits} 學分
          </span>
        )}
        {course.requirement && (
          <span className="shrink-0 rounded-md bg-black/[0.05] px-1.5 py-0.5 text-[10px] font-medium text-[var(--ink-soft)]">
            {course.requirement}
          </span>
        )}
        {course.division && (
          <span className="shrink-0 rounded-md bg-black/[0.05] px-1.5 py-0.5 text-[10px] font-medium text-[var(--ink-soft)]">
            {course.division}
          </span>
        )}
      </span>
      <span className="text-[11px] font-medium text-[var(--ink-soft)]">
        {[course.teachers || "未列教師", course.schedule || "無固定時段", `課號 ${course.offeringId}`].join(" · ")}
      </span>
    </Link>
  );
}
