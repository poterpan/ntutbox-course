// 校園 3D 模型的短效存取 token（D29）。模型放在私有 bucket，由 models.ntutbox.com 的 Worker
// （ntutbox-campus 的 models-worker/）驗證；這裡是發 token 的一端，格式必須與那邊一致：
//   v1.<到期 unix 秒>.<base64url HMAC-SHA256(secret, "v1.<到期>")>
// 兩邊共用 MODEL_TOKEN_SECRET（那邊叫 TOKEN_SECRET）。
export const MODEL_TOKEN_TTL_S = 600;
export const MODEL_BASE_URL = "https://models.ntutbox.com/models/v1";

const enc = new TextEncoder();

function b64url(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

export async function mintModelToken(
  secret: string,
  nowS = Math.floor(Date.now() / 1000),
): Promise<{ token: string; expiresAt: number }> {
  const exp = nowS + MODEL_TOKEN_TTL_S;
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(`v1.${exp}`));
  return { token: `v1.${exp}.${b64url(sig)}`, expiresAt: exp };
}

interface RateLimiter {
  limit(opts: { key: string }): Promise<{ success: boolean }>;
}

export interface ModelTokenEnv {
  MODEL_TOKEN_SECRET?: string;
  MODEL_TOKEN_LIMITER?: RateLimiter;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
      "x-robots-tag": "noindex",
    },
  });

/** GET /api/model-token：只發給本站頁面自己的 fetch（同源），不給跨站、不給直接開網址。
 * 擋不住刻意偽造標頭的腳本——那一層靠模型 Worker 的 UA／頻率限制與短效期。 */
export async function handleModelToken(request: Request, env: ModelTokenEnv): Promise<Response> {
  if (request.method !== "GET") return json({ error: "method" }, 405);
  if (request.headers.get("sec-fetch-site") !== "same-origin") return json({ error: "forbidden" }, 403);
  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin) return json({ error: "forbidden" }, 403);
  if (!env.MODEL_TOKEN_SECRET) return json({ error: "unavailable" }, 503);
  if (env.MODEL_TOKEN_LIMITER) {
    const ip = request.headers.get("cf-connecting-ip") ?? "unknown";
    const { success } = await env.MODEL_TOKEN_LIMITER.limit({ key: ip });
    if (!success) return json({ error: "rate" }, 429);
  }
  const { token, expiresAt } = await mintModelToken(env.MODEL_TOKEN_SECRET);
  return json({ token, expiresAt, base: MODEL_BASE_URL });
}
