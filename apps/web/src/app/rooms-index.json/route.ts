import { loadRoomsCatalog } from "@/lib/rooms/build-rooms";

export const dynamic = "force-static"; // output: export → build 期產出 out/rooms-index.json

/**
 * `/rooms/**` 建構時的教室學期與有頁面的教室代碼（D25）。課程詳情的教室名稱只在
 * 「該課學期＝教室學期且代碼在清單內」時連到教室頁，避免死連結。理由同 /hub-term.json。
 */
export async function GET() {
  const { termKey, rooms } = await loadRoomsCatalog();
  return Response.json({ termKey, codes: rooms.map((r) => r.code) });
}
