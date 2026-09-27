import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import {
  DISPATCH_URL,
  SCHEDULE_URL,
  enableUrl,
  findSlots,
  isKeepaliveHour,
  keepalive,
  run,
  truncateToHour,
  validateSchedule,
} from "../src/scheduler";

const TOKEN = "test-token";
const env = { GITHUB_TOKEN: TOKEN };
const opts = { retryDelayMs: 0 };

function schedule(slots: unknown[]) {
  return { schema_version: 1, calendar_sha256: "abc", slots };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** 依 URL 回應的 fetch mock；dispatch 回應可給序列（依序取用）。 */
function mockFetch(scheduleRes: () => Response | Promise<Response>, dispatchRes: Array<() => Response | Promise<Response>> = []) {
  const fn = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url === SCHEDULE_URL) return scheduleRes();
    if (url === DISPATCH_URL) {
      const next = dispatchRes.shift();
      if (!next) throw new Error("unexpected dispatch call");
      return next();
    }
    throw new Error(`unexpected url ${url}`);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const dispatchCalls = (fn: ReturnType<typeof mockFetch>) => fn.mock.calls.filter(([u]) => String(u) === DISPATCH_URL);

beforeEach(() => {
  vi.spyOn(console, "log").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("時間處理", () => {
  it("scheduledTime 截到整點（容忍 Cloudflare 晚幾分鐘）", () => {
    expect(truncateToHour(Date.parse("2026-10-04T16:07:31.123Z"))).toBe(Date.parse("2026-10-04T16:00:00Z"));
  });

  it("台北時間 slot 以 instant 比對：2026-10-05T00:00+08:00 ＝ 2026-10-04T16:00Z", async () => {
    const fn = mockFetch(
      () => json(schedule([{ at: "2026-10-05T00:00:00+08:00", terms: "115-1", windows: ["期中撤選"], reason: "open-burst" }])),
      [() => new Response(null, { status: 204 })],
    );
    const result = await run(Date.parse("2026-10-04T16:00:00Z"), env, opts);
    expect(result).toEqual({ status: "dispatched", hour: "2026-10-04T16:00:00.000Z", terms: ["115-1"] });
    expect(dispatchCalls(fn)).toHaveLength(1);
  });

  it("findSlots 不會把 UTC 同字面時間當成台北時間", () => {
    const s = schedule([{ at: "2026-10-05T00:00:00+08:00", terms: "115-1" }]) as never;
    expect(findSlots(s, Date.parse("2026-10-05T00:00:00Z"))).toHaveLength(0);
  });
});

describe("dispatch", () => {
  it("命中 slot → POST season.yml，body 與 headers 正確", async () => {
    const fn = mockFetch(
      () => json(schedule([
        { at: "2026-10-05T09:00:00+08:00", terms: "115-1", windows: ["期中撤選"], reason: "base" },
        { at: "2026-10-05T12:00:00+08:00", terms: "115-1", windows: ["期中撤選"], reason: "base" },
      ])),
      [() => new Response(null, { status: 204 })],
    );
    // 故意給 09:02（台北）驗證截整點後仍命中 09:00 的 slot。
    const result = await run(Date.parse("2026-10-05T01:02:00Z"), env, opts);
    expect(result.status).toBe("dispatched");

    const calls = dispatchCalls(fn);
    expect(calls).toHaveLength(1);
    const init = calls[0][1]!;
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ ref: "main", inputs: { terms: "115-1" } });
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe(`Bearer ${TOKEN}`);
    expect(headers.get("Accept")).toBe("application/vnd.github+json");
    expect(headers.get("X-GitHub-Api-Version")).toBe("2022-11-28");
    expect(headers.get("User-Agent")).toBe("ntutbox-season-scheduler");
  });

  it("逗號分隔的 terms 原樣傳遞", async () => {
    const fn = mockFetch(
      () => json(schedule([{ at: "2026-12-07T09:00:00+08:00", terms: "115-1,115-2", windows: ["預選"], reason: "open-burst" }])),
      [() => new Response(null, { status: 204 })],
    );
    await run(Date.parse("2026-12-07T01:00:00Z"), env, opts);
    const body = JSON.parse(String(dispatchCalls(fn)[0][1]!.body));
    expect(body.inputs.terms).toBe("115-1,115-2");
  });

  it("沒有對應 slot → 不呼叫 GitHub", async () => {
    const fn = mockFetch(() => json(schedule([{ at: "2026-10-05T09:00:00+08:00", terms: "115-1" }])));
    const result = await run(Date.parse("2026-10-05T02:00:00Z"), env, opts);
    expect(result.status).toBe("no-slot");
    expect(dispatchCalls(fn)).toHaveLength(0);
  });

  it("排程表 404（尚未發佈）→ 不呼叫 GitHub、不算錯誤", async () => {
    const fn = mockFetch(() => new Response("Not Found", { status: 404 }));
    const result = await run(Date.parse("2026-10-05T01:00:00Z"), env, opts);
    expect(result.status).toBe("no-schedule");
    expect(dispatchCalls(fn)).toHaveLength(0);
    expect(console.error).not.toHaveBeenCalled();
  });

  it("排程表格式錯誤 → 記錯誤、不呼叫 GitHub", async () => {
    const fn = mockFetch(() => json({ schema_version: 2, slots: [] }));
    const result = await run(Date.parse("2026-10-05T01:00:00Z"), env, opts);
    expect(result.status).toBe("schedule-error");
    expect(dispatchCalls(fn)).toHaveLength(0);
    expect(console.error).toHaveBeenCalled();
  });

  it("GitHub 5xx → 重試一次後成功", async () => {
    const fn = mockFetch(
      () => json(schedule([{ at: "2026-10-05T09:00:00+08:00", terms: "115-1" }])),
      [() => new Response("boom", { status: 502 }), () => new Response(null, { status: 204 })],
    );
    const result = await run(Date.parse("2026-10-05T01:00:00Z"), env, opts);
    expect(result.status).toBe("dispatched");
    expect(dispatchCalls(fn)).toHaveLength(2);
  });

  it("GitHub 網路錯誤 → 重試一次；兩次都失敗記錯誤", async () => {
    const fn = mockFetch(
      () => json(schedule([{ at: "2026-10-05T09:00:00+08:00", terms: "115-1" }])),
      [() => Promise.reject(new TypeError("network")), () => Promise.reject(new TypeError("network"))],
    );
    const result = await run(Date.parse("2026-10-05T01:00:00Z"), env, opts);
    expect(result.status).toBe("dispatch-failed");
    expect(dispatchCalls(fn)).toHaveLength(2);
    expect(console.error).toHaveBeenCalled();
  });

  it("GitHub 4xx → 不重試、記下 status 與 body", async () => {
    const fn = mockFetch(
      () => json(schedule([{ at: "2026-10-05T09:00:00+08:00", terms: "115-1" }])),
      [() => new Response('{"message":"Bad credentials"}', { status: 401 })],
    );
    const result = await run(Date.parse("2026-10-05T01:00:00Z"), env, opts);
    expect(result.status).toBe("dispatch-failed");
    expect(dispatchCalls(fn)).toHaveLength(1);
    expect(String(vi.mocked(console.error).mock.calls[0][0])).toContain("401");
    expect(String(vi.mocked(console.error).mock.calls[0][0])).toContain("Bad credentials");
  });

  it("缺 GITHUB_TOKEN → 記錯誤、完全不發請求", async () => {
    const fn = mockFetch(() => json(schedule([{ at: "2026-10-05T09:00:00+08:00", terms: "115-1" }])));
    const result = await run(Date.parse("2026-10-05T01:00:00Z"), {}, opts);
    expect(result.status).toBe("no-token");
    expect(fn).not.toHaveBeenCalled();
    expect(console.error).toHaveBeenCalled();
  });
});

describe("validateSchedule", () => {
  it("接受合法排程表", () => {
    expect(typeof validateSchedule(schedule([{ at: "2026-10-05T09:00:00+08:00", terms: "115-1" }]))).toBe("object");
  });
  it("拒絕缺 terms 或時間不合法的 slot", () => {
    expect(typeof validateSchedule(schedule([{ at: "2026-10-05T09:00:00+08:00" }]))).toBe("string");
    expect(typeof validateSchedule(schedule([{ at: "not-a-date", terms: "115-1" }]))).toBe("string");
    expect(typeof validateSchedule(null)).toBe("string");
  });
});

describe("scheduled handler", () => {
  it("正常無 slot 時不丟例外", async () => {
    mockFetch(() => json(schedule([])));
    await expect(
      worker.scheduled({ scheduledTime: Date.parse("2026-10-05T01:00:00Z"), cron: "0 * * * *" } as ScheduledController, env),
    ).resolves.toBeUndefined();
  });
  it("dispatch 失敗時丟例外（Cron Events 會標失敗）", async () => {
    mockFetch(
      () => json(schedule([{ at: "2026-10-05T09:00:00+08:00", terms: "115-1" }])),
      [() => new Response("nope", { status: 422 })],
    );
    await expect(
      worker.scheduled({ scheduledTime: Date.parse("2026-10-05T01:00:00Z"), cron: "0 * * * *" } as ScheduledController, env),
    ).rejects.toThrow("dispatch-failed");
  });
});

describe("每週保活 daily／weekly", () => {
  const MONDAY_TPE = Date.parse("2026-10-04T16:03:00Z"); // 台北 2026-10-05（週一）00:03
  const ENABLE_URLS = [enableUrl("daily.yml"), enableUrl("weekly.yml")];

  /** schedule 固定空；enable 依 URL 各給回應序列。 */
  function mockAll(enable: Record<string, Array<() => Response | Promise<Response>>> = {}, slots: unknown[] = []) {
    const fn = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url === SCHEDULE_URL) return json(schedule(slots));
      if (url === DISPATCH_URL) return new Response(null, { status: 204 });
      if (ENABLE_URLS.includes(url)) {
        const next = enable[url]?.shift();
        return next ? next() : new Response(null, { status: 204 });
      }
      throw new Error(`unexpected url ${url}`);
    });
    vi.stubGlobal("fetch", fn);
    return fn;
  }
  const enableCalls = (fn: ReturnType<typeof mockAll>) => fn.mock.calls.filter(([u]) => ENABLE_URLS.includes(String(u)));

  it("只有台北週一 00 點（UTC 週日 16 點）是保活整點", () => {
    expect(isKeepaliveHour(truncateToHour(MONDAY_TPE))).toBe(true);
    expect(isKeepaliveHour(Date.parse("2026-10-04T17:00:00Z"))).toBe(false); // 週一 01:00
    expect(isKeepaliveHour(Date.parse("2026-10-05T16:00:00Z"))).toBe(false); // 週二 00:00
    expect(isKeepaliveHour(Date.parse("2026-10-04T00:00:00Z"))).toBe(false); // UTC 週日 00:00＝台北週日 08:00
  });

  it("保活整點 → PUT daily.yml 與 weekly.yml 的 enable，headers 同 dispatch", async () => {
    const fn = mockAll();
    const result = await keepalive(MONDAY_TPE, env, opts);
    expect(result).toEqual({ status: "enabled", workflows: ["daily.yml", "weekly.yml"] });
    const calls = enableCalls(fn);
    expect(calls.map(([u]) => String(u))).toEqual([
      "https://api.github.com/repos/poterpan/ntutbox-course/actions/workflows/daily.yml/enable",
      "https://api.github.com/repos/poterpan/ntutbox-course/actions/workflows/weekly.yml/enable",
    ]);
    for (const [, init] of calls) {
      expect(init!.method).toBe("PUT");
      const headers = new Headers(init!.headers);
      expect(headers.get("Authorization")).toBe(`Bearer ${TOKEN}`);
      expect(headers.get("Accept")).toBe("application/vnd.github+json");
      expect(headers.get("X-GitHub-Api-Version")).toBe("2022-11-28");
      expect(headers.get("User-Agent")).toBe("ntutbox-season-scheduler");
    }
  });

  it("其他整點不呼叫 enable", async () => {
    const fn = mockAll();
    expect(await keepalive(Date.parse("2026-10-05T01:00:00Z"), env, opts)).toEqual({ status: "skipped" });
    expect(fn).not.toHaveBeenCalled();
  });

  it("與 season slot 無關：保活整點沒有 slot 也保活、有 slot 則 dispatch 與保活都做", async () => {
    let fn = mockAll();
    await worker.scheduled({ scheduledTime: MONDAY_TPE, cron: "0 * * * *" } as ScheduledController, env);
    expect(enableCalls(fn)).toHaveLength(2);
    expect(dispatchCalls(fn as never)).toHaveLength(0);

    vi.unstubAllGlobals();
    fn = mockAll({}, [{ at: "2026-10-05T00:00:00+08:00", terms: "115-1" }]);
    await worker.scheduled({ scheduledTime: MONDAY_TPE, cron: "0 * * * *" } as ScheduledController, env);
    expect(enableCalls(fn)).toHaveLength(2);
    expect(dispatchCalls(fn as never)).toHaveLength(1);
  });

  it("非保活整點的 slot 只 dispatch、不 enable", async () => {
    const fn = mockAll({}, [{ at: "2026-10-05T09:00:00+08:00", terms: "115-1" }]);
    await worker.scheduled({ scheduledTime: Date.parse("2026-10-05T01:00:00Z"), cron: "0 * * * *" } as ScheduledController, env);
    expect(enableCalls(fn)).toHaveLength(0);
    expect(dispatchCalls(fn as never)).toHaveLength(1);
  });

  it("一個失敗（4xx）另一個照做；cron 丟例外並點名失敗的 workflow", async () => {
    const fn = mockAll({ [enableUrl("daily.yml")]: [() => new Response('{"message":"Resource not accessible"}', { status: 403 })] });
    const result = await keepalive(MONDAY_TPE, env, opts);
    expect(result).toEqual({ status: "failed", failed: ["daily.yml"] });
    expect(enableCalls(fn)).toHaveLength(2);
    expect(String(vi.mocked(console.error).mock.calls[0][0])).toContain("403");

    vi.unstubAllGlobals();
    mockAll({ [enableUrl("weekly.yml")]: [() => new Response("x", { status: 404 })] });
    await expect(
      worker.scheduled({ scheduledTime: MONDAY_TPE, cron: "0 * * * *" } as ScheduledController, env),
    ).rejects.toThrow("keepalive-failed（weekly.yml）");
  });

  it("5xx 重試一次後成功；網路錯誤兩次 → failed", async () => {
    let fn = mockAll({ [enableUrl("daily.yml")]: [() => new Response("boom", { status: 502 }), () => new Response(null, { status: 204 })] });
    expect((await keepalive(MONDAY_TPE, env, opts)).status).toBe("enabled");
    expect(enableCalls(fn)).toHaveLength(3);

    vi.unstubAllGlobals();
    fn = mockAll({
      [enableUrl("weekly.yml")]: [() => Promise.reject(new TypeError("network")), () => Promise.reject(new TypeError("network"))],
    });
    expect(await keepalive(MONDAY_TPE, env, opts)).toEqual({ status: "failed", failed: ["weekly.yml"] });
  });

  it("缺 GITHUB_TOKEN → 不發請求、回 no-token", async () => {
    const fn = mockAll();
    expect(await keepalive(MONDAY_TPE, {}, opts)).toEqual({ status: "no-token" });
    expect(fn).not.toHaveBeenCalled();
  });
});
