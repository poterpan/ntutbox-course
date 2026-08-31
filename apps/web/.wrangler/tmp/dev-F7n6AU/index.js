var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// src/lib/share/course-link.ts
function buildCourseLink({
  termKey,
  offeringId,
  origin
}) {
  const p = new URLSearchParams({ term: termKey, course: offeringId });
  return `${origin}/?${p.toString()}`;
}
__name(buildCourseLink, "buildCourseLink");

// src/lib/share/og.ts
function planCount(plan) {
  return plan.split(".").filter(Boolean).length;
}
__name(planCount, "planCount");
function resolveShareOg(params, names) {
  const course = params.get("course");
  if (course) {
    const name = names?.[course];
    if (!name) return null;
    const term = params.get("term");
    return {
      title: `${name}\uFF5C\u5317\u79D1\u76D2\u5B50 \u6392\u8AB2`,
      description: `\u67E5\u770B\u5317\u79D1\u300C${name}\u300D\u8AB2\u7A0B\u8CC7\u8A0A\uFF0C\u52A0\u5165\u4F60\u7684\u8AB2\u8868\u3001\u6AA2\u67E5\u885D\u5802\u8207\u5B78\u5206`,
      canonicalPath: term ? buildCourseLink({ termKey: term, offeringId: course, origin: "" }) : null
    };
  }
  const plan = params.get("plan");
  if (plan) {
    const n = planCount(plan);
    if (n < 1) return null;
    return {
      title: `\u5206\u4EAB\u7684\u8AB2\u8868 \xB7 ${n} \u9580\u8AB2\uFF5C\u5317\u79D1\u76D2\u5B50 \u6392\u8AB2`,
      description: `\u67E5\u770B\u9019\u4EFD ${n} \u9580\u8AB2\u7684\u8AB2\u8868\u898F\u5283`,
      canonicalPath: null
    };
  }
  return null;
}
__name(resolveShareOg, "resolveShareOg");

// src/lib/share/course-sitemap.ts
function latestTermKey(termKeys) {
  let best = null;
  let bestVal = -1;
  for (const key of termKeys) {
    const m = /^(\d+)-(\d+)$/.exec(key);
    if (!m) continue;
    const val = Number(m[1]) * 10 + Number(m[2]);
    if (val > bestVal) {
      bestVal = val;
      best = key;
    }
  }
  return best;
}
__name(latestTermKey, "latestTermKey");
function escapeXml(s) {
  return s.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&apos;");
}
__name(escapeXml, "escapeXml");
function buildCourseSitemapXml(origin, termKey, names) {
  const urls = Object.keys(names).sort().map((id) => {
    const loc = buildCourseLink({ termKey, offeringId: id, origin });
    return `<url><loc>${escapeXml(loc)}</loc></url>`;
  });
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls.join("")}</urlset>
`;
}
__name(buildCourseSitemapXml, "buildCourseSitemapXml");

// src/lib/share/course-noscript.ts
function esc(s) {
  return s.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}
__name(esc, "esc");
function clip(s, max) {
  const t = s.replace(/\s+/g, " ").trim();
  return t.length <= max ? t : `${t.slice(0, max)}\u2026`;
}
__name(clip, "clip");
function section(label, value, max = 600) {
  if (!value || !value.trim()) return "";
  return `<h3>${esc(label)}</h3><p>${esc(clip(value, max))}</p>`;
}
__name(section, "section");
function buildCourseNoscriptHtml(detail, termKey, catalog) {
  const name = detail.name?.zh;
  if (!name) return null;
  const syl = (detail.syllabi ?? []).find((s) => s && (s.outline || s.assessment || s.materials));
  const teachers = (catalog?.teachers ?? []).map((t) => t?.name).filter((n) => !!n);
  const teacherName = teachers.join("\u3001") || syl?.teacher_name || "";
  const rooms = (catalog?.classrooms ?? []).map((r) => r?.name).filter((n) => !!n);
  const facts = [];
  if (teacherName) facts.push(`\u6388\u8AB2\u6559\u5E2B\uFF1A${teacherName}`);
  if (catalog?.unit_name) facts.push(`\u958B\u8AB2\u55AE\u4F4D\uFF1A${catalog.unit_name}`);
  if (catalog?.credits != null) facts.push(`\u5B78\u5206\uFF1A${catalog.credits}`);
  if (rooms.length) facts.push(`\u6559\u5BA4\uFF1A${rooms.join("\u3001")}`);
  if (detail.course_code) facts.push(`\u8AB2\u7A0B\u7DE8\u78BC\uFF1A${detail.course_code}`);
  if (detail.offering_id) facts.push(`\u8AB2\u865F\uFF1A${detail.offering_id}`);
  const parts = [
    `<h1>${esc(name)}${detail.name?.en ? `\uFF08${esc(detail.name.en)}\uFF09` : ""}</h1>`,
    `<p>${esc(termKey)} \u5B78\u671F\u30FB\u570B\u7ACB\u81FA\u5317\u79D1\u6280\u5927\u5B78</p>`,
    facts.length ? `<ul>${facts.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : "",
    section("\u8AB2\u7A0B\u6982\u8FF0", detail.description?.zh),
    section("\u6559\u5B78\u5927\u7DB1", syl?.outline, 900),
    section("\u8A55\u91CF\u65B9\u5F0F", syl?.assessment),
    section("\u6559\u6750\u8207\u53C3\u8003\u66F8", syl?.materials, 400),
    // 誠實揭露：這是非官方整理，且此區塊是無 JS 時的替代呈現。
    `<p>\u8CC7\u6599\u6574\u7406\u81EA\u570B\u7ACB\u81FA\u5317\u79D1\u6280\u5927\u5B78\u516C\u958B\u8AB2\u7A0B\u8CC7\u8A0A\u3002\u672C\u7AD9\u70BA\u975E\u5B98\u65B9\u5DE5\u5177\uFF0C\u6B63\u5F0F\u9078\u8AB2\u4EE5\u5B78\u6821\u7CFB\u7D71\u70BA\u6E96\u3002</p>`
  ].filter(Boolean);
  return parts.join("");
}
__name(buildCourseNoscriptHtml, "buildCourseNoscriptHtml");

// worker/index.ts
var SITE_ORIGIN = "https://course.ntutbox.com";
var namesCache = /* @__PURE__ */ new Map();
async function getNames(term, base) {
  const cached = namesCache.get(term);
  if (cached) return cached;
  const res = await fetch(`${base}/terms/${term}/names.json`, {
    cf: { cacheTtl: 3600, cacheEverything: true }
  });
  if (!res.ok) throw new Error(`names ${res.status}`);
  const names = await res.json();
  namesCache.set(term, names);
  return names;
}
__name(getNames, "getNames");
async function getCourseDetail(term, id, base) {
  try {
    const res = await fetch(`${base}/terms/${term}/course/${id}.json`, {
      cf: { cacheTtl: 3600, cacheEverything: true }
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}
__name(getCourseDetail, "getCourseDetail");
var AppendNoscript = class {
  constructor(html) {
    this.html = html;
  }
  static {
    __name(this, "AppendNoscript");
  }
  element(el) {
    el.append(`<noscript>${this.html}</noscript>`, { html: true });
  }
};
var SetContent = class {
  constructor(content) {
    this.content = content;
  }
  static {
    __name(this, "SetContent");
  }
  element(el) {
    el.setAttribute("content", this.content);
  }
};
var SetHref = class {
  constructor(href) {
    this.href = href;
  }
  static {
    __name(this, "SetHref");
  }
  element(el) {
    el.setAttribute("href", this.href);
  }
};
var SetText = class {
  // 欄位不可叫 "text"：HTMLRewriter 會把 handler 物件的 text 屬性當 text-content handler。
  constructor(value) {
    this.value = value;
  }
  static {
    __name(this, "SetText");
  }
  element(el) {
    el.setInnerContent(this.value);
  }
};
async function courseSitemap(env) {
  const res = await fetch(`${env.DATA_BASE_URL}/manifest.json`, {
    cf: { cacheTtl: 3600, cacheEverything: true }
  });
  if (!res.ok) throw new Error(`manifest ${res.status}`);
  const manifest = await res.json();
  const term = latestTermKey(Object.keys(manifest.terms));
  if (!term) throw new Error("no terms");
  const names = await getNames(term, env.DATA_BASE_URL);
  return new Response(buildCourseSitemapXml(SITE_ORIGIN, term, names), {
    headers: {
      "content-type": "application/xml; charset=utf-8",
      "cache-control": "public, max-age=3600",
      // 這份回應是 worker 從零建構的，不經 Static Assets，所以 public/_headers 套不到
      // （實測：/ 與 /og.jpg 有標頭，本路徑 0 個）。XML 不執行腳本、不嵌 iframe，
      // 其餘標頭意義不大，但 nosniff 值得補：避免 MIME 嗅探把它當別的型態處理。
      "x-content-type-options": "nosniff"
    }
  });
}
__name(courseSitemap, "courseSitemap");
var worker = {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/sitemap-courses.xml") {
      try {
        return await courseSitemap(env);
      } catch {
        return new Response("sitemap temporarily unavailable", {
          status: 503,
          headers: { "retry-after": "600" }
        });
      }
    }
    const isShare = url.pathname === "/" && (url.searchParams.has("course") || url.searchParams.has("plan"));
    if (!isShare) return env.ASSETS.fetch(request);
    const assetRes = await env.ASSETS.fetch(request);
    try {
      let names = null;
      const term = url.searchParams.get("term") ?? "";
      if (url.searchParams.has("course") && term) names = await getNames(term, env.DATA_BASE_URL);
      const og = resolveShareOg(url.searchParams, names);
      if (!og) return assetRes;
      const rewriter = new HTMLRewriter().on("title", new SetText(og.title)).on('meta[name="description"]', new SetContent(og.description)).on('meta[property="og:title"]', new SetContent(og.title)).on('meta[property="og:description"]', new SetContent(og.description)).on('meta[name="twitter:title"]', new SetContent(og.title)).on('meta[name="twitter:description"]', new SetContent(og.description));
      if (og.canonicalPath) {
        const canonical = `${SITE_ORIGIN}${og.canonicalPath}`;
        rewriter.on('link[rel="canonical"]', new SetHref(canonical)).on('meta[property="og:url"]', new SetContent(canonical));
      }
      const courseId = url.searchParams.get("course");
      if (courseId && term) {
        const detail = await getCourseDetail(term, courseId, env.DATA_BASE_URL);
        if (detail) {
          const html = buildCourseNoscriptHtml(
            detail,
            term
          );
          if (html) rewriter.on("body", new AppendNoscript(html));
        }
      }
      return rewriter.transform(assetRes);
    } catch {
      return assetRes;
    }
  }
};
var worker_default = worker;

// node_modules/.pnpm/wrangler@4.100.0/node_modules/wrangler/templates/middleware/middleware-ensure-req-body-drained.ts
var drainBody = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } finally {
    try {
      if (request.body !== null && !request.bodyUsed) {
        const reader = request.body.getReader();
        while (!(await reader.read()).done) {
        }
      }
    } catch (e) {
      console.error("Failed to drain the unused request body.", e);
    }
  }
}, "drainBody");
var middleware_ensure_req_body_drained_default = drainBody;

// node_modules/.pnpm/wrangler@4.100.0/node_modules/wrangler/templates/middleware/middleware-miniflare3-json-error.ts
function reduceError(e) {
  return {
    name: e?.name,
    message: e?.message ?? String(e),
    stack: e?.stack,
    cause: e?.cause === void 0 ? void 0 : reduceError(e.cause)
  };
}
__name(reduceError, "reduceError");
var jsonError = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } catch (e) {
    const error = reduceError(e);
    return Response.json(error, {
      status: 500,
      headers: { "MF-Experimental-Error-Stack": "true" }
    });
  }
}, "jsonError");
var middleware_miniflare3_json_error_default = jsonError;

// .wrangler/tmp/bundle-tRdsJF/middleware-insertion-facade.js
var __INTERNAL_WRANGLER_MIDDLEWARE__ = [
  middleware_ensure_req_body_drained_default,
  middleware_miniflare3_json_error_default
];
var middleware_insertion_facade_default = worker_default;

// node_modules/.pnpm/wrangler@4.100.0/node_modules/wrangler/templates/middleware/common.ts
var __facade_middleware__ = [];
function __facade_register__(...args) {
  __facade_middleware__.push(...args.flat());
}
__name(__facade_register__, "__facade_register__");
function __facade_invokeChain__(request, env, ctx, dispatch, middlewareChain) {
  const [head, ...tail] = middlewareChain;
  const middlewareCtx = {
    dispatch,
    next(newRequest, newEnv) {
      return __facade_invokeChain__(newRequest, newEnv, ctx, dispatch, tail);
    }
  };
  return head(request, env, ctx, middlewareCtx);
}
__name(__facade_invokeChain__, "__facade_invokeChain__");
function __facade_invoke__(request, env, ctx, dispatch, finalMiddleware) {
  return __facade_invokeChain__(request, env, ctx, dispatch, [
    ...__facade_middleware__,
    finalMiddleware
  ]);
}
__name(__facade_invoke__, "__facade_invoke__");

// .wrangler/tmp/bundle-tRdsJF/middleware-loader.entry.ts
var __Facade_ScheduledController__ = class ___Facade_ScheduledController__ {
  constructor(scheduledTime, cron, noRetry) {
    this.scheduledTime = scheduledTime;
    this.cron = cron;
    this.#noRetry = noRetry;
  }
  static {
    __name(this, "__Facade_ScheduledController__");
  }
  #noRetry;
  noRetry() {
    if (!(this instanceof ___Facade_ScheduledController__)) {
      throw new TypeError("Illegal invocation");
    }
    this.#noRetry();
  }
};
function wrapExportedHandler(worker2) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return worker2;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  const fetchDispatcher = /* @__PURE__ */ __name(function(request, env, ctx) {
    if (worker2.fetch === void 0) {
      throw new Error("Handler does not export a fetch() function.");
    }
    return worker2.fetch(request, env, ctx);
  }, "fetchDispatcher");
  return {
    ...worker2,
    fetch(request, env, ctx) {
      const dispatcher = /* @__PURE__ */ __name(function(type, init) {
        if (type === "scheduled" && worker2.scheduled !== void 0) {
          const controller = new __Facade_ScheduledController__(
            Date.now(),
            init.cron ?? "",
            () => {
            }
          );
          return worker2.scheduled(controller, env, ctx);
        }
      }, "dispatcher");
      return __facade_invoke__(request, env, ctx, dispatcher, fetchDispatcher);
    }
  };
}
__name(wrapExportedHandler, "wrapExportedHandler");
function wrapWorkerEntrypoint(klass) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return klass;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  return class extends klass {
    #fetchDispatcher = /* @__PURE__ */ __name((request, env, ctx) => {
      this.env = env;
      this.ctx = ctx;
      if (super.fetch === void 0) {
        throw new Error("Entrypoint class does not define a fetch() function.");
      }
      return super.fetch(request);
    }, "#fetchDispatcher");
    #dispatcher = /* @__PURE__ */ __name((type, init) => {
      if (type === "scheduled" && super.scheduled !== void 0) {
        const controller = new __Facade_ScheduledController__(
          Date.now(),
          init.cron ?? "",
          () => {
          }
        );
        return super.scheduled(controller);
      }
    }, "#dispatcher");
    fetch(request) {
      return __facade_invoke__(
        request,
        this.env,
        this.ctx,
        this.#dispatcher,
        this.#fetchDispatcher
      );
    }
  };
}
__name(wrapWorkerEntrypoint, "wrapWorkerEntrypoint");
var WRAPPED_ENTRY;
if (typeof middleware_insertion_facade_default === "object") {
  WRAPPED_ENTRY = wrapExportedHandler(middleware_insertion_facade_default);
} else if (typeof middleware_insertion_facade_default === "function") {
  WRAPPED_ENTRY = wrapWorkerEntrypoint(middleware_insertion_facade_default);
}
var middleware_loader_entry_default = WRAPPED_ENTRY;
export {
  __INTERNAL_WRANGLER_MIDDLEWARE__,
  middleware_loader_entry_default as default
};
//# sourceMappingURL=index.js.map
