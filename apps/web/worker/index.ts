// Cloudflare Worker in front of the static assets. Two jobs:
// 1. Share links (`/?course=` / `/?plan=`): rewrite <title> + description +
//    OG/Twitter meta with the course name / plan size; course links also get a
//    self-canonical + og:url so they can index as long-tail pages.
// 2. `/sitemap-courses.xml`: dynamic sitemap of every course share link in the
//    latest published term (from CDN manifest + names.json).
// Every other request passes straight through to the assets.
// Excluded from the app tsconfig (separate runtime); wrangler bundles it.
import { resolveShareOg } from "../src/lib/share/og";
import { buildCourseSitemapXml, latestTermKey } from "../src/lib/share/course-sitemap";

// Canonical host baked into the static metadata; worker-written canonical /
// og:url / sitemap URLs must match it (preview deploys also point here).
const SITE_ORIGIN = "https://course.ntutbox.com";

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
  setInnerContent(content: string): void;
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

class SetHref {
  constructor(private href: string) {}
  element(el: RewriterElement) {
    el.setAttribute("href", this.href);
  }
}

class SetText {
  // 欄位不可叫 "text"：HTMLRewriter 會把 handler 物件的 text 屬性當 text-content handler。
  constructor(private value: string) {}
  element(el: RewriterElement) {
    el.setInnerContent(this.value);
  }
}

async function courseSitemap(env: Env): Promise<Response> {
  // manifest 不進 isolate cache（會隨新學期改變）；靠 edge cache 撐 1 小時。
  const res = await fetch(`${env.DATA_BASE_URL}/manifest.json`, {
    cf: { cacheTtl: 3600, cacheEverything: true },
  } as RequestInit);
  if (!res.ok) throw new Error(`manifest ${res.status}`);
  const manifest = (await res.json()) as { terms: Record<string, unknown> };
  const term = latestTermKey(Object.keys(manifest.terms));
  if (!term) throw new Error("no terms");
  const names = await getNames(term, env.DATA_BASE_URL);
  return new Response(buildCourseSitemapXml(SITE_ORIGIN, term, names), {
    headers: {
      "content-type": "application/xml; charset=utf-8",
      "cache-control": "public, max-age=3600",
    },
  });
}

const worker = {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/sitemap-courses.xml") {
      try {
        return await courseSitemap(env);
      } catch {
        return new Response("sitemap temporarily unavailable", {
          status: 503,
          headers: { "retry-after": "600" },
        });
      }
    }

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
      const rewriter = new HTMLRewriter()
        .on("title", new SetText(og.title))
        .on('meta[name="description"]', new SetContent(og.description))
        .on('meta[property="og:title"]', new SetContent(og.title))
        .on('meta[property="og:description"]', new SetContent(og.description))
        .on('meta[name="twitter:title"]', new SetContent(og.title))
        .on('meta[name="twitter:description"]', new SetContent(og.description));
      if (og.canonicalPath) {
        const canonical = `${SITE_ORIGIN}${og.canonicalPath}`;
        rewriter
          .on('link[rel="canonical"]', new SetHref(canonical))
          .on('meta[property="og:url"]', new SetContent(canonical));
      }
      return rewriter.transform(assetRes);
    } catch {
      return assetRes; // never break the page
    }
  },
};

export default worker;
