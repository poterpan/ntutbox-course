import { loadHubCatalog } from "@/lib/hub/build-catalog";

export const dynamic = "force-static"; // output: export → build 期產出 out/hub-term.json

/**
 * `/browse/**` hub 建構時用的學期（build 期凍結，與 hub 頁同一次 loadHubCatalog）。
 *
 * 課程詳情的系所 hub 連結只在「正在看的學期＝hub 的學期」時顯示（其他學期的單位可能沒有
 * hub 頁 → 404）。hub 跟的是**部署當下**的預設學期（D21），執行期重算預設學期可能已經換了
 * （例如期中撤選截止後、還沒重新部署）——所以 client 讀這個檔，而不是自己算。
 */
export async function GET() {
  const { termKey } = await loadHubCatalog();
  return Response.json({ termKey });
}
