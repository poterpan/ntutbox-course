/**
 * `/rooms/` — 教室課表索引（D25）：依 GIS 大樓分組列出教室課表學期的全部教室。
 *
 * 靜態 export 實體頁，全部教室的 `<a>` 都寫在 HTML 裡（RoomsDirectory 初次 render 不篩選）。
 * 學期是**本學期**（resolveRoomTerm），不是 hub 的預設學期——見 lib/rooms/room-term.ts。
 */
import type { Metadata } from "next";
import Link from "next/link";
import { loadRoomsCatalog } from "@/lib/rooms/build-rooms";
import { groupRoomsByBuilding } from "@/lib/rooms/rooms-view";
import { HubShell, HubJsonLd, type Crumb } from "@/components/hub/HubShell";
import { RoomsDirectory, type DirectoryGroup } from "@/components/rooms/RoomsDirectory";
import { RoomsNote } from "@/components/rooms/RoomsNote";
import { SITE_ORIGIN } from "@/lib/site";

export const dynamic = "force-static";

const CRUMBS: Crumb[] = [{ label: "北科盒子 排課", href: "/" }, { label: "教室課表" }];

export async function generateMetadata(): Promise<Metadata> {
  const { termKey, rooms } = await loadRoomsCatalog();
  const title = `北科大教室課表・依大樓瀏覽（${termKey}）`;
  const description = `國立臺北科技大學 ${termKey} 學期 ${rooms.length} 間教室的整週課表，依大樓分類。可查每間教室各節排了哪些課、目前這一節依課表有沒有排課。`;
  return {
    title,
    description,
    // 必須覆寫 root layout 的 canonical: "/"（同 /browse/）。
    alternates: { canonical: "/rooms/" },
    openGraph: { title, description, url: `${SITE_ORIGIN}/rooms/`, type: "website" },
  };
}

export default async function RoomsIndexPage() {
  const { termKey, rooms, periods, buildingOrder, checkedAt } = await loadRoomsCatalog();
  const groups: DirectoryGroup[] = groupRoomsByBuilding(rooms, buildingOrder).map((g) => ({
    key: g.buildingId ?? "other",
    buildingName: g.buildingName,
    rooms: g.rooms.map((r) => ({
      code: r.code,
      name: r.name,
      raw: r.raw,
      capacity: r.capacity,
      slotCount: r.slots.length,
      slotKeys: r.slots.map((s) => `${s.day}-${s.period}`),
    })),
  }));
  const periodTable = {
    timezone: periods.timezone ?? "Asia/Taipei",
    periods: (periods.periods ?? []).map((p) => ({ token: p.token, order: p.order, start_hm: p.start_hm, end_hm: p.end_hm })),
  };

  return (
    <>
      <HubJsonLd crumbs={CRUMBS} origin={SITE_ORIGIN} />
      <HubShell
        crumbs={CRUMBS}
        title={`北科大教室課表（${termKey}）`}
        lead={
          <p>
            國立臺北科技大學 <strong className="font-semibold text-[var(--ink)]">{termKey}</strong> 學期共{" "}
            <strong className="font-semibold text-[var(--ink)]">{rooms.length}</strong> 間有排課的教室，依大樓分類。
            點教室看整週課表與「現在／下一堂」；想排自己的課表請到{" "}
            <Link href="/" className="font-medium text-[var(--accent-ink)] hover:underline">
              排課工具
            </Link>
            ，或依系所看{" "}
            <Link href="/browse/" className="font-medium text-[var(--accent-ink)] hover:underline">
              課程總覽
            </Link>
            。
          </p>
        }
      >
        <RoomsDirectory groups={groups} periods={periodTable} />
        <RoomsNote termKey={termKey} checkedAt={checkedAt} />
      </HubShell>
    </>
  );
}
