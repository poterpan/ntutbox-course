import { describe, it, expect } from "vitest";
import {
  PLAN_PAYLOAD_VERSION,
  toIsoDay,
  buildPlanPayload,
  encodePlanPayload,
  buildPlanHandoffURL,
  QR_MAX_CHARS,
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
    expect(p.u).toBe("ntut");
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

  const SURNAMES = ["王","李","張","陳","林","黃","吳","劉","蔡","楊","許","鄭","謝","郭","洪","曾","廖","賴","徐","周"];
  const GIVEN = ["小明","雅婷","建宏","淑芬","家豪","美玲","志偉","怡君","俊傑","佳穎"];
  const BUILDINGS = ["綜合科館","億光大樓","設計館","土木館","電資館","機械館","化工館","人文大樓","共同科館","五族樓"];
  const SUBJECTS = ["微積分","線性代數","資料結構","演算法","作業系統","計算機網路","數位邏輯","電子學","熱力學","材料力學","有機化學","經濟學","會計學","行銷管理","統計學","物理","化學","工程數學","機率論","離散數學"];

  /**
   * 產生 n 門課，**課名／教師／教室三者每門都不同**。
   *
   * 這一點是整個量測的關鍵：deflate 對重複字串壓得極兇，所以「每門課共用同一個
   * 教師名與教室名」的樣本會得出過度樂觀的長度。本檔原先那支 `it.skip` 量測
   * harness 就是那樣寫的（十門課共用「王小明老師」與「綜合科館 502 教室」），
   * 因此它的數字**從來就不等於** `QR_MAX_CHARS` 註解裡記載的那份實測樣本。
   */
  function makePlanOf(n: number) {
    const table: Record<string, CourseOffering> = {};
    const placed: PlacedCourse[] = [];
    for (let i = 0; i < n; i++) {
      const id = `36${1000 + i}`;
      table[id] = {
        offering_id: id,
        name: { zh: `${SUBJECTS[i % SUBJECTS.length]}（${i}）` },
        credits: 3,
        teachers: [{ code: `T${i}`, name: `${SURNAMES[i % SURNAMES.length]}${GIVEN[i % GIVEN.length]}` }],
        classrooms: [{ code: `R${i}`, name: `${BUILDINGS[i % BUILDINGS.length]} ${100 + i * 7} 教室` }],
        requirement: { category: i % 2 ? "elective" : "required", label_zh: "系訂選修" },
        meetings: [{ day: i % 7, periods: ["7", "8"] }],
      } as unknown as CourseOffering;
      placed.push({ offering_id: id, priority: i + 1 });
    }
    return buildPlanPayload({
      termKey: "115-1",
      placed,
      byId: (id: string) => table[id],
      catalogCrawledAt: "2026-08-30T02:11:00Z",
    });
  }

  // 這裡原本只有一支 `it.skip` 的量測 harness——把長度 console.log 出來就結束，
  // 沒有任何斷言。於是 `QR_MAX_CHARS` 這條門檻沒有東西守著：payload 多一個欄位、
  // 壓縮悄悄失效、或課數上限放寬，都可能讓長度跨過門檻，而後果是**桌機的主要
  // 交付路徑（QR）整個消失、退成長連結**，且全部測試依然全綠。
  // 2026-09-04 Codex 稽核點名這一項，改成真斷言。
  //
  // 本產生器 2026-09-04 實測：10 門 794、20 門 1,152、30 門 1,366、40 門 1,574、
  // 60 門 1,980 字元。比 `QR_MAX_CHARS` 註解裡那份 2026-09-03 樣本略好壓
  // （該樣本 10 門 999、30 門 1,859），所以**不要**拿這裡的數字去改那份記錄。

  it("30 門課的預排仍在 QR 門檻內（QR 不會無故消失）", async () => {
    const { encoded, compressed } = await encodePlanPayload(makePlanOf(30));
    // 壓縮失效本身就會讓長度暴增，所以先確認它真的壓了——
    // 否則這條斷言可能因為「根本沒壓但資料剛好夠短」而通過。
    expect(compressed).toBe(true);
    expect(encoded.length).toBeLessThanOrEqual(QR_MAX_CHARS);
  });

  it("20 門課的長度沒有悄悄膨脹（回歸絆線，比門檻更緊）", async () => {
    // 門檻是 2000，而 20 門實測 1,152——直接拿 2000 當斷言的話，payload 要膨脹
    // 七成才會紅，那時桌機 QR 早就在真實資料上壞掉了。這條刻意訂得緊，
    // 目的是讓「多加一個欄位」這種變更當場被看見，而不是等它跨過門檻。
    // 它紅了不代表有 bug，代表要回來重新量、重新決定門檻。
    const { encoded } = await encodePlanPayload(makePlanOf(20));
    expect(encoded.length).toBeLessThanOrEqual(1300);
  });
});
