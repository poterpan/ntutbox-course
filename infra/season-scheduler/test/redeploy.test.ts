import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import { MANIFEST_URL, SCHEDULE_URL, defaultTermSchedule, effectiveHour, findSwitches, redeploy } from "../src/scheduler";

const HOOK = "https://api.cloudflare.com/client/v4/workers/builds/deploy_hooks/test-hook-id";
const env = { DEPLOY_HOOK_URL: HOOK };
const opts = { retryDelayMs: 0 };
/** 115-2 成為預設學期的時刻＝2026-11-21T17:00+08:00＝09:00Z。 */
const SWITCH = Date.parse("2026-11-21T09:00:00Z");

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function manifest(defaults: unknown = [
  { term: "115-1", from: "2026-08-01T00:00:00+08:00" },
  { term: "115-2", from: "2026-11-21T17:00:00+08:00" },
]) {
  return {
    schema_version: 1,
    terms: {},
    term_schedule: { current: [{ term: "115-1", from: "2026-08-01T00:00:00+08:00" }], default: defaults },
  };
}

type Res = () => Response | Promise<Response>;

function mockFetch(manifestRes: Res, hookRes: Res[] = []) {
  const fn = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url === MANIFEST_URL) return manifestRes();
    if (url === HOOK) {
      const next = hookRes.shift();
      if (!next) throw new Error("unexpected hook call");
      return next();
    }
    if (url === SCHEDULE_URL) return new Response("", { status: 404 });
    throw new Error(`unexpected url ${url}`);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const hookCalls = (fn: ReturnType<typeof mockFetch>) => fn.mock.calls.filter(([u]) => String(u) === HOOK);
const ok = () => json({ success: true, errors: [], messages: [], result: { build_uuid: "b", branch: "main", worker: "w" } });

beforeEach(() => {
  vi.spyOn(console, "log").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("term_schedule 解析", () => {
  it("缺 term_schedule／default 不是陣列 → null", () => {
    expect(defaultTermSchedule({ schema_version: 1 })).toBeNull();
    expect(defaultTermSchedule({ term_schedule: {} })).toBeNull();
    expect(defaultTermSchedule({ term_schedule: { default: "x" } })).toBeNull();
    expect(defaultTermSchedule(null)).toBeNull();
  });

  it("略過形狀不對的項目", () => {
    const entries = defaultTermSchedule(manifest([{ term: "115-2", from: "not-a-date" }, { term: 1 }, { term: "115-2", from: "2026-11-21T17:00:00+08:00" }]));
    expect(entries).toEqual([{ term: "115-2", from: "2026-11-21T17:00:00+08:00" }]);
  });

  it("整點上的 from＝截整點；非整點取下一個整點（不在切換前 build）", () => {
    expect(effectiveHour(SWITCH)).toBe(SWITCH);
    expect(effectiveHour(SWITCH + 30 * 60 * 1000)).toBe(SWITCH + 60 * 60 * 1000);
  });

  it("以 instant 比對：+08:00 的 17:00 不等於 UTC 17:00", () => {
    const e = [{ term: "115-2", from: "2026-11-21T17:00:00+08:00" }];
    expect(findSwitches(e, SWITCH)).toHaveLength(1);
    expect(findSwitches(e, Date.parse("2026-11-21T17:00:00Z"))).toHaveLength(0);
  });
});

describe("redeploy", () => {
  it("缺 secret → no-hook，不發任何請求", async () => {
    const fn = mockFetch(() => json(manifest()));
    expect(await redeploy(SWITCH, {}, opts)).toEqual({ status: "no-hook" });
    expect(fn).not.toHaveBeenCalled();
    expect(String(vi.mocked(console.log).mock.calls[0][0])).toContain("no deploy hook, skip");
  });

  it("manifest 沒有 term_schedule → skip、不打 hook", async () => {
    const fn = mockFetch(() => json({ schema_version: 1, terms: {} }));
    expect(await redeploy(SWITCH, env, opts)).toEqual({ status: "no-term-schedule" });
    expect(hookCalls(fn)).toHaveLength(0);
  });

  it("非切換整點 → no-switch", async () => {
    const fn = mockFetch(() => json(manifest()));
    expect(await redeploy(SWITCH + 3600_000, env, opts)).toEqual({ status: "no-switch", hour: "2026-11-21T10:00:00.000Z" });
    expect(hookCalls(fn)).toHaveLength(0);
  });

  it("切換整點（Cloudflare 晚幾分鐘也算）→ POST hook、無 body", async () => {
    const fn = mockFetch(() => json(manifest()), [ok]);
    const result = await redeploy(SWITCH + 4 * 60_000, env, opts);
    expect(result).toEqual({ status: "triggered", hour: "2026-11-21T09:00:00.000Z", terms: ["115-2"] });
    const [, init] = hookCalls(fn)[0];
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeUndefined();
  });

  it("5xx 重試一次後成功", async () => {
    const fn = mockFetch(() => json(manifest()), [() => new Response("boom", { status: 503 }), ok]);
    expect((await redeploy(SWITCH, env, opts)).status).toBe("triggered");
    expect(hookCalls(fn)).toHaveLength(2);
  });

  it("網路錯誤兩次 → trigger-failed；log 不含 hook URL", async () => {
    const fn = mockFetch(() => json(manifest()), [
      () => Promise.reject(new TypeError("network")),
      () => Promise.reject(new TypeError("network")),
    ]);
    expect((await redeploy(SWITCH, env, opts)).status).toBe("trigger-failed");
    expect(hookCalls(fn)).toHaveLength(2);
    const logged = [...vi.mocked(console.error).mock.calls, ...vi.mocked(console.warn).mock.calls].flat().join("\n");
    expect(logged).not.toContain("test-hook-id");
  });

  it("4xx 不重試 → trigger-failed", async () => {
    const fn = mockFetch(() => json(manifest()), [() => json({ success: false }, 404)]);
    expect((await redeploy(SWITCH, env, opts)).status).toBe("trigger-failed");
    expect(hookCalls(fn)).toHaveLength(1);
  });

  it("manifest 讀取失敗 → manifest-error", async () => {
    mockFetch(() => new Response("nope", { status: 404 }));
    expect((await redeploy(SWITCH, env, opts)).status).toBe("manifest-error");
  });
});

describe("scheduled handler × redeploy", () => {
  const controller = { scheduledTime: SWITCH, cron: "0 * * * *" } as ScheduledController;

  it("與 season 無關：沒有 GITHUB_TOKEN 也照樣觸發 hook（但 no-token 仍讓 cron 標失敗）", async () => {
    const fn = mockFetch(() => json(manifest()), [ok]);
    await expect(worker.scheduled(controller, env)).rejects.toThrow("no-token");
    expect(hookCalls(fn)).toHaveLength(1);
  });

  it("hook 失敗 → cron 丟例外並點名 redeploy", async () => {
    mockFetch(() => json(manifest()), [() => json({ success: false }, 404)]);
    await expect(worker.scheduled(controller, { ...env, GITHUB_TOKEN: "t" })).rejects.toThrow("redeploy-trigger-failed");
  });

  it("缺 secret 不算失敗", async () => {
    mockFetch(() => json(manifest()));
    await expect(worker.scheduled(controller, { GITHUB_TOKEN: "t" })).resolves.toBeUndefined();
  });
});
