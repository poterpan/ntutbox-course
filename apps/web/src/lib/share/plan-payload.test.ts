import { describe, it, expect } from "vitest";
import {
  PLAN_PAYLOAD_VERSION,
  toIsoDay,
  buildPlanPayload,
  encodePlanPayload,
  buildPlanHandoffURL,
} from "./plan-payload";
import type { CourseOffering } from "@/lib/data/types";
import type { PlacedCourse } from "@/store/draft-store";

const calc = {
  offering_id: "360744",
  name: { zh: "微積分（一）" },
  credits: 3,
  teachers: [{ code: "T1", name: "王小明" }],
  classrooms: [{ code: "R1", name: "綜科館 502" }],
  requirement: { category: "required", label_zh: "部訂必修" },
  meetings: [{ day: 1, periods: ["7", "8"] }],
} as unknown as CourseOffering;

const sunday = {
  offering_id: "360801",
  name: { zh: "週日課" },
  credits: null,
  teachers: [],
  classrooms: [],
  meetings: [{ day: 0, periods: ["1"] }],
} as unknown as CourseOffering;

const table: Record<string, CourseOffering> = { "360744": calc, "360801": sunday };
const byId = (id: string) => table[id];
const placed: PlacedCourse[] = [
  { offering_id: "360744", priority: 1 },
  { offering_id: "360801", priority: 2 },
];

describe("toIsoDay", () => {
  it("週日 0 對應到 ISO 的 7，其餘不變", () => {
    expect(toIsoDay(0)).toBe(7);
    expect(toIsoDay(1)).toBe(1);
    expect(toIsoDay(6)).toBe(6);
  });
});

describe("buildPlanPayload", () => {
  it("組出 spec §3 的欄位形狀", () => {
    const p = buildPlanPayload({
      termKey: "115-1",
      placed,
      byId,
      catalogCrawledAt: "2026-08-30T02:11:00Z",
      now: 1725336000_000,
    });
    expect(p.t).toBe("115-1");
    expect(p.d).toBe("2026-08-30T02:11:00Z");
    expect(p.x).toBe(1725336000);
    expect(p.c).toHaveLength(2);
    expect(p.c[0]).toEqual({
      i: "360744",
      n: "微積分（一）",
      r: 3,
      h: ["王小明"],
      m: [[1, "78"]],
      l: "綜科館 502",
      q: "required",
      p: 1,
      s: 1,
    });
  });

  it("星期 0（週日）轉成 7；學分為 null 保留 null", () => {
    const p = buildPlanPayload({ termKey: "115-1", placed, byId });
    expect(p.c[1].m).toEqual([[7, "1"]]);
    expect(p.c[1].r).toBeNull();
  });

  it("catalogCrawledAt 取不到就省略 d 欄位", () => {
    const p = buildPlanPayload({ termKey: "115-1", placed, byId, catalogCrawledAt: null });
    expect("d" in p).toBe(false);
  });

  it("requirement 缺失時 category 退為 unknown", () => {
    const bare = { offering_id: "X", name: { zh: "X" }, meetings: [] } as unknown as CourseOffering;
    const p = buildPlanPayload({
      termKey: "115-1",
      placed: [{ offering_id: "X", priority: 1 }],
      byId: (id) => (id === "X" ? bare : undefined),
    });
    expect(p.c[0].q).toBe("unknown");
    expect(p.c[0].h).toEqual([]);
    expect(p.c[0].l).toBe("");
  });

  it("教師／教室 name 為空字串時 fallback 到 code，不會整個從陣列消失", () => {
    // EntityRef.name 在 crawler/models.py 預設是 "" 而非 None，
    // 所以真實資料裡「沒有姓名」長這樣：{ code: "T9", name: "" }。
    // 若誤用 ?? 只在 null/undefined 才 fallback，空字串會直接穿過，
    // 再被 filter(Boolean) 濾掉——整個 entity 從 h/l 消失，而不是退顯示 code。
    const emptyName = {
      offering_id: "Y",
      name: { zh: "Y" },
      teachers: [{ code: "T9", name: "" }],
      classrooms: [{ code: "R9", name: "" }],
      meetings: [],
    } as unknown as CourseOffering;
    const p = buildPlanPayload({
      termKey: "115-1",
      placed: [{ offering_id: "Y", priority: 1 }],
      byId: (id) => (id === "Y" ? emptyName : undefined),
    });
    expect(p.c[0].h).toEqual(["T9"]);
    expect(p.c[0].l).toBe("R9");
  });

  it("credits 為 0 時保留 0，不退為 null", () => {
    // 刻意與上一題方向相反：0 是有效學分（0 學分課存在），要保留；
    // 只有 credits 真的缺席（undefined）才退為 null。所以這裡用 ??
    // 而不是 ||——別看到 name 那題改用 || 就順手把這裡也統一，
    // 會把 0 學分課的學分變成「未知」。
    const zeroCredit = {
      offering_id: "Z",
      name: { zh: "Z" },
      credits: 0,
      meetings: [],
    } as unknown as CourseOffering;
    const p = buildPlanPayload({
      termKey: "115-1",
      placed: [{ offering_id: "Z", priority: 1 }],
      byId: (id) => (id === "Z" ? zeroCredit : undefined),
    });
    expect(p.c[0].r).toBe(0);
  });
});

describe("encodePlanPayload / buildPlanHandoffURL", () => {
  it("壓縮後可 round-trip 回原 payload", async () => {
    const p = buildPlanPayload({ termKey: "115-1", placed, byId });
    const { encoded, compressed } = await encodePlanPayload(p);
    expect(compressed).toBe(true);

    // 用與 App／落地頁相同的解碼路徑驗證
    let t = encoded.replace(/-/g, "+").replace(/_/g, "/");
    while (t.length % 4 !== 0) t += "=";
    const bin = atob(t);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    // 不用 Blob().stream()：jsdom 的 Blob 沒有該方法（見 plan-payload.ts 的註解）
    const stream = new ReadableStream<Uint8Array<ArrayBuffer>>({
      start(c) {
        c.enqueue(bytes);
        c.close();
      },
    }).pipeThrough(new DecompressionStream("deflate-raw"));
    const out = new Uint8Array(await new Response(stream).arrayBuffer());
    expect(JSON.parse(new TextDecoder().decode(out))).toEqual(p);
  });

  it("編碼結果只含 base64url 字元（可安全放進 fragment）", async () => {
    const p = buildPlanPayload({ termKey: "115-1", placed, byId });
    const { encoded } = await encodePlanPayload(p);
    expect(encoded).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it("連結形狀是 /plan/#v=&e=&p=，且 payload 不被百分比編碼", () => {
    const url = buildPlanHandoffURL({ encoded: "abc-_123", compressed: true });
    expect(url).toBe(`https://ntutbox.com/plan/#v=${PLAN_PAYLOAD_VERSION}&e=1&p=abc-_123`);
  });

  it("未壓縮時 e=0", () => {
    const url = buildPlanHandoffURL({ encoded: "abc", compressed: false, origin: "https://x.test" });
    expect(url).toBe(`https://x.test/plan/#v=${PLAN_PAYLOAD_VERSION}&e=0&p=abc`);
  });

  it.skip("量測用：印出 10 門課的 payload 長度", async () => {
    const tenTable: Record<string, CourseOffering> = {};
    const tenPlaced: PlacedCourse[] = [];
    for (let i = 0; i < 10; i++) {
      const id = `36${1000 + i}`;
      tenTable[id] = {
        offering_id: id,
        name: { zh: `測試課程名稱範例 ${i}` },
        credits: 3,
        teachers: [{ code: `T${i}`, name: "王小明老師" }],
        classrooms: [{ code: `R${i}`, name: "綜合科館 502 教室" }],
        requirement: { category: "elective", label_zh: "系訂選修" },
        meetings: [{ day: i % 7, periods: ["7", "8"] }],
      } as unknown as CourseOffering;
      tenPlaced.push({ offering_id: id, priority: i + 1 });
    }
    const tenById = (id: string) => tenTable[id];
    const p = buildPlanPayload({
      termKey: "115-1",
      placed: tenPlaced,
      byId: tenById,
      catalogCrawledAt: "2026-08-30T02:11:00Z",
    });
    const { encoded, compressed } = await encodePlanPayload(p);
    console.log("courses:", p.c.length, "compressed:", compressed, "encoded chars:", encoded.length);
  });
});
