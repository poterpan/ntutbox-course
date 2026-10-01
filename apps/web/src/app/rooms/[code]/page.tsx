/**
 * `/rooms/<code>/` — 單間教室的整週課表（D25）。URL 用學校教室代碼（跨學期穩定，見 spec）。
 *
 * 靜態 HTML 內含課表（課名、教師、課程頁連結）；「現在／下一堂」由 RoomTimetable 在 mount 後算。
 * URL 不帶學期：教室頁跟著教室學期（本學期）走，學期寫在頁面內容裡。
 */
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { loadRoomsCatalog } from "@/lib/rooms/build-rooms";
import { roomHref, type RoomView } from "@/lib/rooms/rooms-view";
import { HubShell, HubSection, HubJsonLd, type Crumb } from "@/components/hub/HubShell";
import { RoomTimetable } from "@/components/rooms/RoomTimetable";
import { RoomsNote } from "@/components/rooms/RoomsNote";
import { SITE_ORIGIN } from "@/lib/site";

export const dynamic = "force-static";
// static export 不允許 dynamicParams: true；不在清單的代碼 → 404。
export const dynamicParams = false;

export async function generateStaticParams() {
  const { rooms } = await loadRoomsCatalog();
  return rooms.map((r) => ({ code: r.code }));
}

async function resolveRoom(code: string) {
  const catalog = await loadRoomsCatalog();
  const room = catalog.rooms.find((r) => r.code === decodeURIComponent(code));
  if (!room) notFound();
  return { ...catalog, room };
}

function roomStats(room: RoomView) {
  const courses = new Set<string>();
  for (const s of room.slots) for (const c of s.courses) courses.add(c.offeringId);
  return { periodCount: room.slots.length, courseCount: courses.size };
}

export async function generateMetadata({ params }: { params: Promise<{ code: string }> }): Promise<Metadata> {
  const { code } = await params;
  const { termKey, room } = await resolveRoom(code);
  const s = roomStats(room);
  const title = `${room.name} 教室課表（${termKey}）`;
  const description = `國立臺北科技大學 ${room.buildingName === "其他" ? "" : room.buildingName}${room.raw}（${room.name}）${termKey} 學期整週課表：每週 ${s.periodCount} 節、${s.courseCount} 門課${room.capacity != null ? `，容量 ${room.capacity} 人` : ""}。依課表查這間教室各節排了什麼課。`;
  return {
    title,
    description,
    // 必須覆寫 root layout 的 canonical: "/"（同 /browse/）。
    alternates: { canonical: roomHref(room.code) },
    openGraph: { title, description, url: `${SITE_ORIGIN}${roomHref(room.code)}`, type: "website" },
  };
}

export default async function RoomPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const { termKey, room, periods, checkedAt } = await resolveRoom(code);
  const s = roomStats(room);
  const crumbs: Crumb[] = [
    { label: "北科盒子 排課", href: "/" },
    { label: "教室課表", href: "/rooms/" },
    { label: room.raw },
  ];
  const gridPeriods = [...(periods.periods ?? [])]
    .sort((a, b) => a.order - b.order)
    .map((p) => ({ token: p.token, start_hm: p.start_hm, end_hm: p.end_hm }));

  return (
    <>
      <HubJsonLd crumbs={crumbs} origin={SITE_ORIGIN} />
      <HubShell
        crumbs={crumbs}
        title={`${room.name} 教室課表（${termKey}）`}
        lead={
          <p>
            {room.buildingName !== "其他" && <>{room.buildingName}・</>}
            {room.raw}（代碼 {room.code}）
            {room.capacity != null && <>，容量 {room.capacity} 人</>}。{termKey} 學期依課表每週排了{" "}
            <strong className="font-semibold text-[var(--ink)]">{s.periodCount}</strong> 節、
            <strong className="font-semibold text-[var(--ink)]">{s.courseCount}</strong> 門課。點課名可在排課工具開啟課程詳情。
          </p>
        }
      >
        <HubSection title={`${termKey} 週課表`} note="依學校教室課表；同一格可能有多門課">
          <RoomTimetable timezone={periods.timezone ?? "Asia/Taipei"} periods={gridPeriods} slots={room.slots} />
        </HubSection>
        <p className="text-sm">
          <Link href="/rooms/" className="font-medium text-[var(--accent-ink)] hover:underline">
            ← 全部教室
          </Link>
        </p>
        <RoomsNote termKey={termKey} checkedAt={checkedAt} />
      </HubShell>
    </>
  );
}
