// 匯出到 App 的 wire format。完整定義見 NTUTBox repo 的
// docs/superpowers/specs/2026-09-03-course-plan-draft-import-design.md §3。
//
// 這個格式有三份實作：本檔（編碼）、官網 /plan 落地頁（解碼）、App 的
// CoursePlanLinkParser（解碼）。**唯一真相來源是那份 spec**，任何欄位語意
// 變更都要遞增 PLAN_PAYLOAD_VERSION，不可原地改。
//
// payload 放在 URL fragment，所以永遠不會送達伺服器（不進 Cloudflare / GA log）。

import { submitOrder } from "@/lib/planner/submit-order";
import type { CourseOffering } from "@/lib/data/types";
import type { PlacedCourse } from "@/store/draft-store";

export const PLAN_PAYLOAD_VERSION = 1;

/**
 * QR 密度上限。2026-09-03 用「每門課名稱／教師／教室皆不同」的真實形狀樣本實測
 * （deflate-raw + base64url）：10 門 999、15 門 1,224、20 門 1,442、30 門 1,859 字元。
 * QR byte mode 在 level L 的硬上限是 2,953 bytes，所以這些都在容量內，真正的限制是
 * 好不好掃。門檻取 2000 而不是更緊：20 門課是很正常的一份預排（滿修＋備選），
 * 把它擋在 QR 之外會讓桌機使用者無故退回複製連結。
 * 未壓縮（`e=0`）的 10 門課是 2,742 字元 → 自然超過門檻、不給 QR，這是刻意的。
 *
 * 住在這裡而不是 `ExportToAppDialog`：這是 payload 編碼的性質（壓縮後的 base64url
 * 長度），不是那個對話框的 UI 性質。放在 lib 才能讓 payload 的測試直接引用它，
 * 而不是把 2000 這個數字複製第二份——複製之後兩邊會各自漂移，而漂移的那一天
 * 不會有任何測試變紅。
 */
export const QR_MAX_CHARS = 2000;

export interface PlanPayloadCourse {
  /** offering_id（課號） */
  i: string;
  /** 課名 */
  n: string;
  /** 學分，可為 null（有 0 / 0.5 佔位課） */
  r: number | null;
  /** 教師姓名 */
  h: string[];
  /** [ISO-8601 星期 1..7, 節次 token 串接] */
  m: [number, string][];
  /** 教室顯示名，多間以「、」串接 */
  l: string;
  /** requirement.category */
  q: string;
  /** 志願序，連續 1..N */
  p: number;
  /** 1 = 第一志願、2 = 衝堂備選 */
  s: 1 | 2;
}

export interface PlanPayload {
  /**
   * 學校代碼，目前只接受 "ntut"。必填——排課站只有北科課表，但這個保證只在
   * 送出端成立；接收端（App）靠這個欄位斷言來源，缺欄或值不符即拒收。
   * 見 spec §3〈學校 provenance 在接收端強制〉。
   */
  u: "ntut";
  /** term_key，例 "115-1" */
  t: string;
  /** 課程資料爬取時間（ISO 8601）。取不到就省略；不參與任何邏輯判斷 */
  d?: string;
  /** 匯出時間，unix 秒 */
  x: number;
  c: PlanPayloadCourse[];
}

/** 排課站的 Day 是 0..6（0 = 週日）；wire format 用 ISO-8601 1..7（7 = 週日）。 */
export function toIsoDay(day: number): number {
  return day === 0 ? 7 : day;
}

export function buildPlanPayload(args: {
  termKey: string;
  placed: PlacedCourse[];
  byId: (id: string) => CourseOffering | undefined;
  catalogCrawledAt?: string | null;
  now?: number;
}): PlanPayload {
  const { termKey, placed, byId, catalogCrawledAt, now } = args;

  const c: PlanPayloadCourse[] = submitOrder(placed, byId).map((o) => {
    // submitOrder 已剔除 byId 查不到的課號，這裡的 ! 是安全的
    const src = byId(o.offeringId)!;
    return {
      i: src.offering_id,
      n: src.name?.zh ?? src.offering_id,
      // credits 用 ?? ：0 是有效學分（0 學分課存在），只有欄位真的缺席
      // （undefined）才退為 null。
      r: src.credits ?? null,
      // teacher/classroom 的 name 用 || 而非 ??：crawler/models.py 的
      // EntityRef.name 預設值是 ""（不是 Optional[str] = None），所以真實
      // 資料裡「沒有姓名」是空字串。?? 只在 null/undefined 才 fallback，
      // 空字串會直接穿過再被下面的 filter(Boolean) 濾掉——整個 entity 從
      // h/l 消失，而不是退顯示 code。與 credits 的 ?? 方向刻意相反，別為了
      // 「統一運算子」而互相套用。
      h: (src.teachers ?? []).map((t) => t.name || t.code).filter((v): v is string => !!v),
      m: (src.meetings ?? []).map(
        (mt) => [toIsoDay(mt.day), mt.periods.join("")] as [number, string],
      ),
      l: (src.classrooms ?? [])
        .map((r) => r.name || r.code)
        .filter((v): v is string => !!v)
        .join("、"),
      q: src.requirement?.category ?? "unknown",
      p: o.priority,
      s: o.tier,
    };
  });

  return {
    u: "ntut",
    t: termKey,
    ...(catalogCrawledAt ? { d: catalogCrawledAt } : {}),
    x: Math.floor((now ?? Date.now()) / 1000),
    c,
  };
}

/**
 * 刻意不用 `new Blob([...]).stream()`。jsdom 的 Blob **沒有** `.stream()`，
 * 所以那個寫法在瀏覽器可行、但在 vitest（`environment: "jsdom"`）會直接
 * TypeError。2026-09-03 實測：jsdom 下 CompressionStream / DecompressionStream /
 * Response / ReadableStream 都存在且可用，只有 Blob.stream() 缺。
 *  回傳型別明確標成 `Uint8Array<ArrayBuffer>`：TS 5.7+ 的 lib.dom 把 TypedArray
 *  換成泛型（`Uint8Array<ArrayBufferLike>`），型別停在裸 `Uint8Array` 會在
 *  `pipeThrough(DecompressionStream)` 那行對不上宣告的 `Uint8Array<ArrayBuffer>`，
 *  `next build` / `tsc --noEmit` 會直接失敗（2026-09-03 於 ntutbox-website 實撞）。
 */
function bytesToStream(bytes: Uint8Array<ArrayBuffer>): ReadableStream<Uint8Array<ArrayBuffer>> {
  return new ReadableStream<Uint8Array<ArrayBuffer>>({
    start(c) {
      c.enqueue(bytes);
      c.close();
    },
  });
}

function base64urlFromBytes(bytes: Uint8Array<ArrayBuffer>): string {
  // 不用 String.fromCharCode(...bytes)：payload 上千 bytes 會爆呼叫堆疊
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * deflate-raw（RFC 1951）+ base64url。與 App 端的
 * `(data as NSData).decompressed(using: .zlib)` 對稱——Apple 的 .zlib 就是 raw DEFLATE。
 * 環境不支援 CompressionStream 時降級為未壓縮（呼叫端要據此隱藏 QR）。
 */
export async function encodePlanPayload(
  payload: PlanPayload,
): Promise<{ encoded: string; compressed: boolean }> {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  if (typeof CompressionStream === "undefined") {
    return { encoded: base64urlFromBytes(bytes), compressed: false };
  }
  try {
    const stream = bytesToStream(bytes).pipeThrough(new CompressionStream("deflate-raw"));
    const out = new Uint8Array(await new Response(stream).arrayBuffer());
    return { encoded: base64urlFromBytes(out), compressed: true };
  } catch {
    return { encoded: base64urlFromBytes(bytes), compressed: false };
  }
}

export function buildPlanHandoffURL(args: {
  encoded: string;
  compressed: boolean;
  origin?: string;
}): string {
  // 手寫而非 URLSearchParams：base64url 的 - 與 _ 雖然不會被百分比編碼，
  // 但這個字串要逐字對得上 App 端的解析，明寫最不會出意外。
  const base = args.origin ?? "https://ntutbox.com";
  const e = args.compressed ? "1" : "0";
  return `${base}/plan/#v=${PLAN_PAYLOAD_VERSION}&e=${e}&p=${args.encoded}`;
}
