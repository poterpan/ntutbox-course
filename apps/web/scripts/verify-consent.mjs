#!/usr/bin/env node
/**
 * GA4 opt-in 的瀏覽器驗收：對 `out/` 的真實靜態產物跑完整同意生命週期。
 * （官網 ntutbox-website/scripts/verify-consent.mjs 的排課站版本，結構刻意保持一致。）
 *
 * 為什麼需要這支（單元測試補不上的部分）：
 * - 單元測試把 `next/script` mock 掉了，「dataLayer 順序在真瀏覽器裡真的正確」只能真跑。
 * - 「同意前零 Google 請求」是隱私承諾。unit test 只能斷言元件沒 render，
 *   真正該證明的是**網路層一個請求都沒發**。
 * - **page_title（collect 的 `dt`）**：edge worker 會把分享連結的 `<title>` 改寫成
 *   「⟨課名⟩｜北科盒子 排課」／「分享的課表 · N 門課｜…」，而 GA4 預設自動收集 page_title。
 *   本腳本會**照 worker 的規則改寫本機 HTML 的 title**，再驗證 dataLayer 與真實 collect
 *   請求裡的 title 都是固定值、不含課名。這是 2026-08-18 驗收抓到的漏洞的回歸測試。
 *
 * 刻意**不進 CI**：Cloudflare Workers Builds 只跑 `pnpm install && pnpm build`，
 * 為一支手動驗收把 playwright 塞進 devDependencies 會讓每次 production build 都多下載瀏覽器。
 * 因此 playwright 用「自備」策略，見下方 usage。
 *
 * 用法：
 *   1. 用啟用 GA 的 env 建置（out/ 必須含 Measurement ID，否則本腳本拒跑）：
 *        NEXT_PUBLIC_GA_MEASUREMENT_ID=G-TEST123456 \
 *        NEXT_PUBLIC_GA_ENABLED=true NEXT_PUBLIC_GA_DEBUG=true pnpm build
 *      （DEBUG=true 必要：hostname allowlist 只放行 ntutbox.com 三個網域，本機驗收得靠它
 *        放行 localhost。務必搭配**測試用** Measurement ID，別用 production 的。）
 *      不要設 NEXT_PUBLIC_DATA_BASE_URL——要走 out/data/v1 的本機 fixtures。
 *   2. 自備 playwright，二擇一：
 *        pnpm add -D playwright        # 用完記得移除，別提交
 *        # 或指向既有安裝：PLAYWRIGHT_PATH=/path/to/node_modules/playwright/index.mjs
 *   3. pnpm verify:consent
 *
 * 環境變數：PLAYWRIGHT_PATH（playwright 模組路徑）、PORT（預設 4322）。
 */
import { createServer } from "node:http";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join, normalize } from "node:path";

const OUT = "out";
const PORT = Number(process.env.PORT ?? 4322);
const BASE = `http://localhost:${PORT}`;
const GOOGLE = /googletagmanager\.com|google-analytics\.com|\/g\/collect|doubleclick\.net/;
const FIXED_TITLE = "北科盒子 排課"; // = src/lib/analytics/config.ts PAGE_TITLE
const TERM = "115-1";

// ── 前置檢查：out/ 必須是「啟用 GA」的建置，否則整份驗收沒有意義 ──
if (!existsSync(join(OUT, "index.html"))) {
  console.error(`✗ 找不到 ${OUT}/index.html——請先 pnpm build`);
  process.exit(2);
}
const chunkDir = join(OUT, "_next", "static", "chunks");
const hasId =
  existsSync(chunkDir) &&
  readdirSync(chunkDir).some(
    (f) => f.endsWith(".js") && /G-[A-Z0-9]{4,20}/.test(readFileSync(join(chunkDir, f), "utf8")),
  );
if (!hasId) {
  console.error(
    "✗ out/ 不含 Measurement ID：這份建置沒啟用 GA，驗收會全部假通過。\n" +
      "  請用檔頭 usage 的 env 重新 pnpm build。",
  );
  process.exit(2);
}
const namesPath = join(OUT, "data", "v1", "terms", TERM, "names.json");
if (!existsSync(namesPath)) {
  console.error(`✗ 找不到 ${namesPath}——分享連結的 title 改寫驗收需要本機 fixtures`);
  process.exit(2);
}
// 拿一門真實課程來重現 worker 的 title 改寫（課名是公開資料）。挑前 20 門裡名字最長的，
// 讓「payload 不含課名」的字串比對足夠銳利（"國文" 這種兩字名容易誤判成通過）。
const names = JSON.parse(readFileSync(namesPath, "utf8")); // { offering_id: 課名 }
const [SHARE_OID, SHARE_NAME] = Object.entries(names)
  .slice(0, 20)
  .reduce((best, e) => (e[1].length > best[1].length ? e : best));

// ── playwright 自備（不進 devDependencies，理由見檔頭）──
let chromium;
try {
  ({ chromium } = await import(process.env.PLAYWRIGHT_PATH ?? "playwright"));
} catch {
  console.error(
    "✗ 找不到 playwright。請 `pnpm add -D playwright`（用完移除），\n" +
      "  或用 PLAYWRIGHT_PATH 指向既有安裝（見檔頭 usage）。",
  );
  process.exit(2);
}

// ── 最小靜態伺服器 ──
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
  ".xml": "application/xml; charset=utf-8",
};
const server = createServer((req, res) => {
  const url = new URL(req.url, BASE);
  const path = normalize(decodeURIComponent(url.pathname)).replace(/^(\.\.[/\\])+/, "");
  let file = join(OUT, path);
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
  if (!existsSync(file)) {
    res.writeHead(404).end("not found");
    return;
  }
  let body = readFileSync(file);
  // 重現 worker/index.ts 對分享連結的 <title> 改寫（見 src/lib/share/og.ts resolveShareOg），
  // 這樣「hydration 後 document.title 帶課名」的 production 條件才會在本機成立。
  if (path === "/index.html" || path === "/") {
    const course = url.searchParams.get("course");
    const plan = url.searchParams.get("plan");
    const title =
      course && names[course]
        ? `${names[course]}｜北科盒子 排課`
        : plan
          ? `分享的課表 · ${plan.split(".").filter(Boolean).length} 門課｜北科盒子 排課`
          : null;
    if (title) body = Buffer.from(String(body).replace(/<title>[^<]*<\/title>/, `<title>${title}</title>`));
  }
  res.writeHead(200, { "content-type": MIME[extname(file)] ?? "application/octet-stream" });
  res.end(body);
});
await new Promise((resolve) => server.listen(PORT, resolve));

const results = [];
const check = (name, ok, detail = "") =>
  results.push({ name, ok, detail: typeof detail === "string" ? detail : JSON.stringify(detail) });
const skip = (name, why) => results.push({ name, skipped: true, ok: true, detail: why });
// 觀測值（不判斷對錯，只留證據——例如真實 collect payload 的 dt 到底長什麼樣）。
const observations = [];
const info = (label, value) => observations.push(`${label}: ${JSON.stringify(value)}`);
const dataLayerOf = (page, filter) =>
  page.evaluate(
    ([f]) =>
      (window.dataLayer ?? [])
        .map((e) => Array.from(e))
        .filter((e) => !f || (e[0] === f[0] && e[1] === f[1]))
        .map((e) => (f ? e[2] : e)),
    [filter],
  );
const configArgOf = (page) =>
  page.evaluate(() =>
    (window.dataLayer ?? []).map((e) => Array.from(e)).filter((e) => e[0] === "config").map((e) => e[2]),
  );
/** collect 請求的某個 query 參數（GA4 payload：dt=page_title、dl=page_location）。 */
const paramsOf = (urls, key) =>
  urls.filter((u) => u.includes("/collect")).map((u) => new URL(u).searchParams.get(key));

// 用系統 Chrome：本機常見的是 playwright 版本與已下載 chromium 不匹配
const browser = await chromium.launch({ channel: "chrome" });

/** 已同意、且 localStorage/sessionStorage 全新的 context——各 case 互不污染
 * （草稿會讓「排入」變成「已排」、plan_created 的 session guard 也會擋掉第二次）。 */
async function grantedContext() {
  const c = await browser.newContext();
  await c.addCookies([{ name: "ntutbox_analytics_consent", value: "granted_v1", url: BASE }]);
  await c.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE });
  return c;
}
/** 「＋ 排入」按鈕；aria-label 要 exact，否則會誤中「已排入，點擊查看或退選」。 */
const placeButton = (p) => p.getByLabel("排入", { exact: true }).first();

try {
  const ctx = await browser.newContext();
  await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE });
  const page = await ctx.newPage();
  const googleHits = [];
  page.on("request", (r) => {
    if (GOOGLE.test(r.url())) googleHits.push(r.url());
  });

  // ── 1. 首次造訪：同意前不得有任何 Google 請求 ──
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  check("同意前無任何 Google 請求", googleHits.length === 0, googleHits.join(", "));
  // 同意前 window.gtag 是**本地 shim**（§4 允許先建 dataLayer 並把四項設成 denied，
  // 這不載入任何 Google 資源）。要驗的是它只做了 consent 記帳：沒有 config、沒有 event。
  const preConsent = (await dataLayerOf(page)).map((e) => `${e[0]}|${e[1]}`);
  check(
    "同意前 dataLayer 只有 consent default（無 config／event）",
    preConsent.length === 1 && preConsent[0] === "consent|default",
    preConsent.join(" / "),
  );
  check(
    "同意前沒有 consent cookie",
    !(await page.evaluate(() => document.cookie)).includes("ntutbox_analytics_consent"),
    await page.evaluate(() => document.cookie),
  );
  check("同意 UI 出現", await page.getByRole("button", { name: "同意" }).isVisible());
  check("拒絕按鈕同樣可見", await page.getByRole("button", { name: "拒絕" }).isVisible());
  check(
    "同意 UI 不遮住主要動作（匯出/分享仍可見）",
    (await page.getByRole("button", { name: /匯出到 App/ }).isVisible()) &&
      (await page.getByRole("button", { name: /分享課表/ }).isVisible()),
  );

  // ── 2. 按下同意 ──
  await page.getByRole("button", { name: "同意" }).click();
  await page.waitForTimeout(2000);

  check(
    "同意後寫入 granted_v1",
    (await page.evaluate(() => document.cookie)).includes("ntutbox_analytics_consent=granted_v1"),
  );
  check("同意 UI 收起", (await page.getByRole("button", { name: "同意" }).count()) === 0);
  check(
    "同意後才請求 gtag.js",
    googleHits.some((u) => u.includes("googletagmanager.com/gtag/js")),
    googleHits.slice(0, 3).join(", "),
  );
  check("同意後 window.gtag 已定義", (await page.evaluate(() => typeof window.gtag)) === "function");

  const commands = (await dataLayerOf(page)).map((e) => `${e[0]}|${e[1]}`);
  check("dataLayer 有 consent default", commands.includes("consent|default"), commands.join(" / "));
  check("dataLayer 有 consent update", commands.includes("consent|update"));
  check(
    "consent default 在 update 之前",
    commands.indexOf("consent|default") < commands.indexOf("consent|update"),
  );

  const [defaultArg] = await dataLayerOf(page, ["consent", "default"]);
  const [updateArg] = await dataLayerOf(page, ["consent", "update"]);
  check(
    "default 四項皆 denied",
    ["analytics_storage", "ad_storage", "ad_user_data", "ad_personalization"].every(
      (k) => defaultArg?.[k] === "denied",
    ),
    defaultArg,
  );
  check("update 後 analytics_storage granted", updateArg?.analytics_storage === "granted", updateArg);
  check("update 後 ad_personalization 仍 denied", updateArg?.ad_personalization === "denied", updateArg);

  const [configArg] = await configArgOf(page);
  check("config 關閉自動 page_view", configArg?.send_page_view === false, configArg);
  check("config cookie_domain=auto", configArg?.cookie_domain === "auto");
  check("config 帶固定 page_title", configArg?.page_title === FIXED_TITLE, configArg?.page_title);

  const pageViews = await dataLayerOf(page, ["event", "page_view"]);
  check("送出恰好一次 page_view", pageViews.length === 1, `count=${pageViews.length}`);
  check("page_view 帶 site_surface=course", pageViews[0]?.site_surface === "course", pageViews[0]);

  // ── 3. 排課／分享／匯出三個接點（事件參數只能有 enum 與 bucket）──
  await placeButton(page).click();
  await page.waitForTimeout(300);
  const added = await dataLayerOf(page, ["event", "course_added"]);
  const created = await dataLayerOf(page, ["event", "plan_created"]);
  check("course_added 送出且 placement=course_list", added[0]?.placement === "course_list", added[0]);
  check("course_added 用 bucket 而非精確數", added[0]?.placed_count_bucket === "1", added[0]);
  check("首次排入送出一次 plan_created", created.length === 1, created);

  await page.getByRole("button", { name: /分享課表/ }).click();
  await page.waitForTimeout(500);
  const shared = await dataLayerOf(page, ["event", "plan_shared"]);
  check(
    "plan_shared 送出且 share_method/bucket 正確",
    shared[0]?.share_method === "copy" && shared[0]?.course_count_bucket === "1",
    shared[0],
  );

  await page.getByRole("button", { name: /匯出到 App/ }).click();
  await page.waitForTimeout(300);
  const exported = await dataLayerOf(page, ["event", "export_to_app_click"]);
  check(
    "export_to_app_click 送出且 handoff_method=placeholder",
    exported[0]?.handoff_method === "placeholder",
    exported[0],
  );

  const allEvents = JSON.stringify(await dataLayerOf(page));
  check(
    "所有事件參數都不含課號／課名／搜尋原文",
    !allEvents.includes(SHARE_OID) && !allEvents.includes(SHARE_NAME),
    allEvents.slice(0, 200),
  );

  // ── 4. 分享連結：worker 改寫過的 <title> 不得流進 GA（page_title / collect 的 dt）──
  const ctx4 = await grantedContext();
  const page4 = await ctx4.newPage();
  const hits4 = [];
  page4.on("request", (r) => {
    if (GOOGLE.test(r.url())) hits4.push(r.url());
  });
  // 先證明「HTML 層的 title 真的帶課名」——直接抓伺服器回應，不經瀏覽器。
  const servedHtml = await (await fetch(`${BASE}/?term=${TERM}&course=${SHARE_OID}`)).text();
  check(
    `前提：HTML 的 <title> 確實帶課名（${SHARE_NAME}）`,
    (servedHtml.match(/<title>([^<]*)<\/title>/)?.[1] ?? "").includes(SHARE_NAME),
    servedHtml.match(/<title>[^<]*<\/title>/)?.[0] ?? "(找不到 title)",
  );

  await page4.goto(`${BASE}/?term=${TERM}&course=${SHARE_OID}`, { waitUntil: "networkidle" });
  await page4.waitForTimeout(1500);
  // Next 的 flight payload 也帶著 metadata title，hydration 會把 worker 改寫的 title 蓋回預設值
  // （在 out/index.html 裡那串 title 出現 4 次可證）。所以 hydration 之後讀到什麼不該當成斷言基礎，
  // 只記錄下來；真正要守的是「不管 document.title 是什麼，GA 都送固定值」——下面直接把它改成
  // 帶課名的樣子再送事件，這條斷言就不可能假通過（也涵蓋日後有人動態改 title 的情況）。
  const afterHydration = await page4.title();
  await page4.evaluate((t) => {
    document.title = t;
  }, `${SHARE_NAME}｜北科盒子 排課`);
  // 分享連結會開這門課的詳情窗（overlay 蓋住背後清單），就從窗內排入——正好是收到分享連結的真實路徑。
  await page4.getByRole("button", { name: /排入課表/ }).click();
  await page4.waitForTimeout(600);

  const titles4 = [
    ...(await configArgOf(page4)).map((c) => c?.page_title),
    ...(await page4.evaluate(() =>
      (window.dataLayer ?? []).map((e) => Array.from(e)).filter((e) => e[0] === "set").map((e) => e[1]?.page_title),
    )),
  ];
  check(
    "page_title 恆為固定值（即使 document.title 帶課名）",
    titles4.length > 0 && titles4.every((t) => t === FIXED_TITLE),
    `titles=${JSON.stringify(titles4)} / document.title=${await page4.title()} / hydration 後=${afterHydration}`,
  );
  check(
    "dataLayer 全文不含課名／課號",
    !JSON.stringify(await dataLayerOf(page4)).includes(SHARE_NAME) &&
      !JSON.stringify(await dataLayerOf(page4)).includes(SHARE_OID),
    JSON.stringify(await dataLayerOf(page4)).slice(0, 200),
  );
  const dts = paramsOf(hits4, "dt");
  info(`分享連結的 ${dts.length} 個 collect 請求，dt 觀測值`, [...new Set(dts)]);
  info("同一批 collect 的 dl（page_location）觀測值", [...new Set(paramsOf(hits4, "dl"))]);
  if (dts.length === 0) {
    skip(
      "collect 的 dt 為固定值",
      "測試用 Measurement ID 不會觸發 /g/collect（GA 對不存在的 property 不發 hit）；" +
        "dataLayer 層已驗，dt 直接取自 page_title",
    );
  } else {
    check("collect 的 dt 為固定值、不含課名", dts.every((dt) => dt === FIXED_TITLE), JSON.stringify(dts));
  }
  check(
    "collect 請求全文不含課名／課號",
    hits4.every((u) => !decodeURIComponent(u).includes(SHARE_NAME) && !u.includes(SHARE_OID)),
    hits4.filter((u) => u.includes("/collect")).slice(0, 2).join(" ") || "(尚無 collect 請求)",
  );
  await page4.close();

  // ── 5. 帶敏感 query 的網址：清洗必須生效（含真實 collect 請求）──
  const ctx5 = await grantedContext();
  const page5 = await ctx5.newPage();
  const hits5 = [];
  page5.on("request", (r) => {
    if (GOOGLE.test(r.url())) hits5.push(r.url());
  });
  await page5.goto(
    `${BASE}/?term=${TERM}&plan=360744.360745&payload=secret&token=tok&utm_source=google&gclid=abc123#frag`,
    { waitUntil: "networkidle" },
  );
  await page5.waitForTimeout(1800);
  const [set5] = await page5.evaluate(() =>
    (window.dataLayer ?? []).map((e) => Array.from(e)).filter((e) => e[0] === "set").map((e) => e[1]),
  );
  const pv5 = await dataLayerOf(page5, ["event", "page_view"]);
  check(
    "page_location 保留 UTM 與 gclid",
    set5?.page_location?.includes("utm_source=google") && set5?.page_location?.includes("gclid=abc123"),
    set5,
  );
  check(
    "page_location 移除 plan/payload/token/hash",
    !JSON.stringify(set5).includes("360744") &&
      !JSON.stringify(set5).includes("secret") &&
      !JSON.stringify(set5).includes("tok") &&
      !JSON.stringify(set5).includes("frag"),
    set5,
  );
  // ?term 在分享連結上會被 use-share-link 先 replaceState 清掉（它的 effect 在 GA 的 effect 之前跑），
  // 所以這裡只保證「網址裡不留 term=」；term_key 有沒有帶不強制（分享連統的 term_key 只是 nice-to-have，
  // 排課事件本身都從 term-store 取 term_key）。廣告落地頁 `?term=115-1`（沒有 course/plan）不會被清，
  // 由下一個 case 正面驗證。
  check(
    "term 不留在 page_location（term_key 若有必須合法）",
    !set5?.page_location?.includes("term=") && [undefined, TERM].includes(pv5[0]?.term_key),
    `term_key=${pv5[0]?.term_key} / ${set5?.page_location}`,
  );
  check(
    "分享課表連結的 title 不洩漏精確課數（page_title 固定）",
    set5?.page_title === FIXED_TITLE,
    `${set5?.page_title} / document.title=${await page5.title()}`,
  );
  const collect5 = hits5.filter((u) => u.includes("/collect"));
  check(
    "實際 collect 請求不含敏感值",
    collect5.every((u) => !u.includes("360744") && !u.includes("secret") && !/[?&]tok/.test(u)),
    collect5.slice(0, 2).join(" ") || "(尚無 collect 請求)",
  );
  await page5.close();

  // ── 5b. 廣告落地頁（§8 的 Final URL）：term_key 必須送出、UTM 保留 ──
  const ctxAd = await grantedContext();
  const pageAd = await ctxAd.newPage();
  await pageAd.goto(`${BASE}/?term=${TERM}&utm_source=google&utm_medium=cpc&utm_campaign=1151_adddrop`, {
    waitUntil: "networkidle",
  });
  await pageAd.waitForTimeout(1500);
  const pvAd = await dataLayerOf(pageAd, ["event", "page_view"]);
  check("廣告落地頁 page_view 帶 term_key", pvAd[0]?.term_key === TERM, pvAd[0]);
  // campaign_key 只在 export_to_app_click 附帶，這裡驗它有被記進 sessionStorage 的 enum
  check(
    "utm_campaign 只存成固定 enum",
    (await pageAd.evaluate(() => sessionStorage.getItem("ntutbox_campaign_key"))) === "google_ads_1151",
    await pageAd.evaluate(() => sessionStorage.getItem("ntutbox_campaign_key")),
  );
  await placeButton(pageAd).click();
  await pageAd.getByRole("button", { name: /匯出到 App/ }).click();
  await pageAd.waitForTimeout(400);
  const exportAd = await dataLayerOf(pageAd, ["event", "export_to_app_click"]);
  check("export_to_app_click 帶 campaign_key", exportAd[0]?.campaign_key === "google_ads_1151", exportAd[0]);
  await pageAd.close();

  // ── 6. 拒絕路徑（全新 context，模擬新訪客）──
  const ctx2 = await browser.newContext();
  const page6 = await ctx2.newPage();
  const hits6 = [];
  page6.on("request", (r) => {
    if (GOOGLE.test(r.url())) hits6.push(r.url());
  });
  await page6.goto(BASE, { waitUntil: "networkidle" });
  await page6.getByRole("button", { name: "拒絕" }).click();
  await page6.waitForTimeout(800);
  check(
    "拒絕後寫入 denied_v1",
    (await page6.evaluate(() => document.cookie)).includes("ntutbox_analytics_consent=denied_v1"),
  );
  await page6.reload({ waitUntil: "networkidle" });
  await page6.waitForTimeout(1200);
  check("拒絕後維持不載入", hits6.length === 0, hits6.join(", "));
  check("拒絕後不再詢問", (await page6.getByRole("button", { name: "同意" }).count()) === 0);
  check(
    "拒絕後排課仍可用（分析不影響產品）",
    await placeButton(page6).isVisible(),
  );
  await placeButton(page6).click();
  await page6.waitForTimeout(300);
  // 拒絕後 dataLayer 只會有本地 consent 記帳（default + update denied），不得有 config／event。
  const afterDeny = (await dataLayerOf(page6)).map((e) => `${e[0]}|${e[1]}`);
  check(
    "拒絕後排入不送任何事件（dataLayer 只有 consent 記帳）",
    afterDeny.every((c) => c.startsWith("consent|")),
    afterDeny.join(" / "),
  );
} finally {
  await browser.close();
  server.close();
}

const failed = results.filter((r) => !r.ok);
const skipped = results.filter((r) => r.skipped);
for (const r of results) {
  const tag = r.skipped ? "SKIP" : r.ok ? "PASS" : "FAIL";
  console.log(`${tag}  ${r.name}${r.ok && !r.skipped ? "" : `  → ${r.detail}`}`);
}
if (observations.length) {
  console.log("\n觀測值（證據）：");
  for (const o of observations) console.log(`  · ${o}`);
}
if (failed.length) {
  console.error(`\n✗ verify-consent 失敗（${failed.length}/${results.length}）`);
  process.exit(1);
}
console.log(
  `\n✓ verify-consent 全部通過（${results.length - skipped.length}/${results.length}` +
    `${skipped.length ? `，${skipped.length} 項 SKIP` : ""}）`,
);
