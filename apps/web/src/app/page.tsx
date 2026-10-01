import { PlannerLayout } from "@/components/planner/PlannerLayout";
import { HomeIntro } from "@/components/home/HomeIntro";
import { loadHubCatalog } from "@/lib/hub/build-catalog";
import { loadRoomsCatalog } from "@/lib/rooms/build-rooms";
import { buildHomeSummary } from "@/lib/home/home-summary";

export const dynamic = "force-static";

export default async function Page() {
  // build 期資料（同 /browse/、/rooms/ 共用的快取）。教室資料缺席不擋首頁：介紹區只少一格數據。
  const hub = await loadHubCatalog();
  const rooms = await loadRoomsCatalog().catch((e) => {
    console.warn(`[home] 教室資料載入失敗（${e instanceof Error ? e.message : e}），首頁不顯示教室數`);
    return null;
  });
  return (
    <>
      <PlannerLayout />
      <HomeIntro summary={buildHomeSummary({ hub, rooms })} />
    </>
  );
}
