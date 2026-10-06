import { createHmac } from "node:crypto";
import { describe, expect, it } from "vitest";
import { handleModelToken, mintModelToken, MODEL_BASE_URL } from "./model-token";

const req = (headers: Record<string, string>, method = "GET") =>
  new Request("https://course.ntutbox.com/api/model-token", { method, headers });
const SAME = { "sec-fetch-site": "same-origin" };

describe("mintModelToken", () => {
  it("signs v1.<exp> with HMAC-SHA256, same as the models Worker", async () => {
    // 期望值用 node:crypto 依格式獨立計算（WebCrypto 之外的另一套實作）；models-worker 的測試驗同一條規格。
    const secret = "unit-test-only";
    const exp = 1800000000 + 600;
    const sig = createHmac("sha256", secret).update(`v1.${exp}`).digest("base64url");
    expect(await mintModelToken(secret, 1800000000)).toEqual({ token: `v1.${exp}.${sig}`, expiresAt: exp });
  });
});

describe("handleModelToken", () => {
  const env = { MODEL_TOKEN_SECRET: "s" };

  it("issues a no-store token to same-origin fetches", async () => {
    const res = await handleModelToken(req(SAME), env);
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    const body = (await res.json()) as { token: string; base: string };
    expect(body.token).toMatch(/^v1\.\d{10}\.[A-Za-z0-9_-]{43}$/);
    expect(body.base).toBe(MODEL_BASE_URL);
  });

  it("refuses navigation, cross-site and spoofed-origin requests", async () => {
    expect((await handleModelToken(req({ "sec-fetch-site": "none" }), env)).status).toBe(403);
    expect((await handleModelToken(req({ "sec-fetch-site": "cross-site" }), env)).status).toBe(403);
    expect((await handleModelToken(req({}), env)).status).toBe(403);
    expect(
      (await handleModelToken(req({ ...SAME, origin: "https://evil.example" }), env)).status,
    ).toBe(403);
    expect((await handleModelToken(req(SAME, "POST"), env)).status).toBe(405);
  });

  it("fails closed without a secret and honours the rate limiter", async () => {
    expect((await handleModelToken(req(SAME), {})).status).toBe(503);
    const limited = { ...env, MODEL_TOKEN_LIMITER: { limit: async () => ({ success: false }) } };
    expect((await handleModelToken(req(SAME), limited)).status).toBe(429);
  });
});
