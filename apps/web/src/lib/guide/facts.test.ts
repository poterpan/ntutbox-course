import { describe, expect, it } from "vitest";
import {
  GE_DIMENSIONS,
  MPROGRAM_CATEGORIES,
  PERIOD_TABLE,
  REQUIREMENT_LEGEND,
  SELECTION_ERRORS,
  SELECTION_MECHANISMS,
  SOURCE_GAPS,
} from "./facts";

/**
 * 這些是**對外公開的制度事實**，錯了會誤導學生選課。每一條在 facts.ts 都標了來源；
 * 測試把來源那一刻的值釘住，之後若有人「順手改一下」會立刻紅燈，逼他回去核對來源。
 */
describe("guide facts — 節次", () => {
  it("節次順序是 1234N56789ABCD，共 14 節（不是 1..14）", () => {
    // 來源：CLAUDE.md 關鍵事實 + crawler/ntut_catalog/periods.py 的 PERIOD_ORDER
    expect(PERIOD_TABLE.map((p) => p.token).join("")).toBe("1234N56789ABCD");
    expect(PERIOD_TABLE).toHaveLength(14);
  });

  it("牆鐘時間與 crawler/ntut_catalog/periods.py 一致（抽樣）", () => {
    const byToken = new Map(PERIOD_TABLE.map((p) => [p.token, p]));
    expect([byToken.get("1")!.start, byToken.get("1")!.end]).toEqual(["08:10", "09:00"]);
    expect([byToken.get("N")!.start, byToken.get("N")!.end]).toEqual(["12:10", "13:00"]);
    expect([byToken.get("A")!.start, byToken.get("A")!.end]).toEqual(["18:30", "19:20"]);
    expect([byToken.get("D")!.start, byToken.get("D")!.end]).toEqual(["21:10", "22:00"]);
  });

  it("每一節都有 HH:MM 格式的起訖", () => {
    for (const p of PERIOD_TABLE) {
      expect(p.start).toMatch(/^\d{2}:\d{2}$/);
      expect(p.end).toMatch(/^\d{2}:\d{2}$/);
    }
  });
});

describe("guide facts — 修別符號", () => {
  it("六個官方圖例符號都在，且必／選標對", () => {
    // 來源：crawler/ntut_catalog/requirement_legend.py（Cprog.jsp?format=-5 官方圖例）
    const bySymbol = new Map(REQUIREMENT_LEGEND.map((r) => [r.symbol, r]));
    expect([...bySymbol.keys()]).toEqual(["○", "△", "☆", "●", "▲", "★"]);
    expect(bySymbol.get("△")!.label).toBe("校訂共同必修");
    expect(bySymbol.get("▲")!.label).toBe("校訂專業必修");
    expect(bySymbol.get("☆")!.kind).toBe("選修");
    expect(bySymbol.get("★")!.kind).toBe("選修");
  });

  it("只有 △▲☆★ 標成開課清單出現過（○● 官方圖例有、資料中未見）", () => {
    const seen = REQUIREMENT_LEGEND.filter((r) => r.seenInCatalog).map((r) => r.symbol);
    expect(seen.sort()).toEqual(["★", "☆", "△", "▲"].sort());
  });
});

describe("guide facts — 通識與微學程", () => {
  it("博雅四向度", () => {
    // 來源：115-1 課程資料中博雅課程備註欄出現的向度字串
    expect(GE_DIMENSIONS).toEqual(["人文與藝術", "社會與法治", "自然與科學", "創新與創業"]);
  });

  it("微學程課程分類與 crawler/models.py 的 MProgramCategory 一致", () => {
    expect(MPROGRAM_CATEGORIES).toEqual(["基礎", "核心", "總整", "進階", "應用"]);
  });
});

describe("guide facts — 選課機制", () => {
  it("四種機制都在，且各自標了處理範圍", () => {
    // 來源：docs/DESIGN.md §4.6（114-2 期末預選公告）+ CLAUDE.md 選課階段分類
    expect(SELECTION_MECHANISMS.map((m) => m.name)).toEqual([
      "期末網路初選",
      "志願選填（分發制）",
      "開學後加退選",
      "獨立登記（不經選課系統）",
    ]);
    for (const m of SELECTION_MECHANISMS) {
      expect(m.scope.length).toBeGreaterThan(0);
      expect(m.note).not.toBe("");
    }
  });

  it("志願分發機制涵蓋博雅／體育／共同英文", () => {
    const ballot = SELECTION_MECHANISMS.find((m) => m.name.startsWith("志願選填"))!;
    expect(ballot.scope.join("|")).toContain("博雅");
    expect(ballot.scope.join("|")).toContain("體育");
    expect(ballot.scope.join("|")).toContain("共同英文");
  });

  it("獨立登記標明不經選課系統（微學程最常見的誤會）", () => {
    const reg = SELECTION_MECHANISMS.find((m) => m.name.startsWith("獨立登記"))!;
    expect(reg.where).toContain("教務處");
    expect(reg.scope.join("|")).toContain("微學程");
  });

  it("常見錯誤訊息表每條都有意思與下一步", () => {
    expect(SELECTION_ERRORS.map((e) => e.message)).toContain("※不是本班課程※");
    for (const e of SELECTION_ERRORS) {
      expect(e.meaning).not.toBe("");
      expect(e.next).not.toBe("");
    }
  });
});

describe("guide facts — 來源缺口", () => {
  it("誠實列出來源沒有的四類資訊", () => {
    // 來源：CLAUDE.md「來源根本沒有的」+ docs/DESIGN.md §4.7
    const what = SOURCE_GAPS.map((g) => g.what).join("|");
    expect(what).toContain("單雙週");
    expect(what).toContain("教室");
    expect(what).toContain("人數上限");
    expect(what).toContain("班週會");
  });
});

describe("guide facts — 不得出現會逐年變動的數字", () => {
  /**
   * 稽核要求：不確定或逐年變動的制度細節不寫（選課日期、學分上下限、應修學分）。
   * 這個測試掃整份 facts 的字串內容，攔下「順手加上去」的日期與學分門檻。
   */
  it("沒有具體日期或學分上下限數字", () => {
    const text = JSON.stringify([
      SELECTION_MECHANISMS,
      SELECTION_ERRORS,
      SOURCE_GAPS,
      GE_DIMENSIONS,
      MPROGRAM_CATEGORIES,
    ]);
    expect(text).not.toMatch(/\d{1,2}\s*[/月]\s*\d{1,2}/); // 6/8、6 月 8 日
    expect(text).not.toMatch(/\d+\s*[-~－～]\s*\d+\s*學分/); // 16-25 學分
    expect(text).not.toMatch(/至少\s*\d+\s*學分/);
  });
});
