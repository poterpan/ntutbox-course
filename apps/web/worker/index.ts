// Cloudflare Worker in front of the static assets. For share links
// (`/?course=` / `/?plan=`) it rewrites the OG meta with the course name /
// plan size; every other request passes straight through to the assets.
// Excluded from the app tsconfig (separate runtime); wrangler bundles it.
import { resolveShareOg } from "../src/lib/share/og";

// Minimal Workers-runtime types (avoids a global @cloudflare/workers-types
// dependency that would pollute the Next app's DOM lib typings).
interface Fetcher {
  fetch(input: Request): Promise<Response>;
}
interface Env {
  ASSETS: Fetcher;
  DATA_BASE_URL: string;
}
interface RewriterElement {
  setAttribute(name: string, value: string): void;
}
declare class HTMLRewriter {
  on(selector: string, handlers: { element(el: RewriterElement): void }): HTMLRewriter;
  transform(res: Response): Response;
}

// Best-effort per-isolate cache: term → names map. Fresh isolates re-fetch;
// new terms use a new key, so nothing needs manual invalidation.
const namesCache = new Map<string, Record<string, string>>();

async function getNames(term: string, base: string): Promise<Record<string, string>> {
  const cached = namesCache.get(term);
  if (cached) return cached;
  const res = await fetch(`${base}/terms/${term}/names.json`, {
    cf: { cacheTtl: 3600, cacheEverything: true },
  } as RequestInit);
  if (!res.ok) throw new Error(`names ${res.status}`);
  const names = (await res.json()) as Record<string, string>;
  namesCache.set(term, names);
  return names;
}

class SetContent {
  constructor(private content: string) {}
  element(el: RewriterElement) {
    el.setAttribute("content", this.content);
  }
}

const worker = {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const isShare =
      url.pathname === "/" && (url.searchParams.has("course") || url.searchParams.has("plan"));
    if (!isShare) return env.ASSETS.fetch(request);

    const assetRes = await env.ASSETS.fetch(request); // SPA index.html
    try {
      let names: Record<string, string> | null = null;
      const term = url.searchParams.get("term") ?? "";
      if (url.searchParams.has("course") && term) names = await getNames(term, env.DATA_BASE_URL);
      const og = resolveShareOg(url.searchParams, names);
      if (!og) return assetRes;
      return new HTMLRewriter()
        .on('meta[property="og:title"]', new SetContent(og.title))
        .on('meta[property="og:description"]', new SetContent(og.description))
        .on('meta[name="twitter:title"]', new SetContent(og.title))
        .on('meta[name="twitter:description"]', new SetContent(og.description))
        .transform(assetRes);
    } catch {
      return assetRes; // never break the page
    }
  },
};

export default worker;
