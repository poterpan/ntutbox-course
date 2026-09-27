// ntutbox-season-scheduler：選課季 season.yml 的準時觸發器（issue #111）。
//
// 為什麼不用 GitHub cron：實測每小時排程約 74% 被吞、每日排程延遲中位 2.4 小時。
// 所以改由 Cloudflare Cron 每小時整點醒來，讀 CDN 上的排程表
// （由 Python 端從行事曆解析產出），命中「這個整點」的 slot 才 dispatch season.yml。
//
// 窗口判斷全部在 Python 端完成；本 worker 只做「查表＋呼叫 GitHub API」，刻意保持笨。
//
// 邏輯放在這個檔、index.ts 只放 handler：workerd 把 entry module 的每個具名匯出都當成
// handler，匯出常數或函式會讓 runtime 啟動失敗。

export interface Env {
  GITHUB_TOKEN?: string;
  /** Workers Builds Deploy Hook（ntutbox-course-web、main）；未設＝不做自動重新部署（D22）。 */
  DEPLOY_HOOK_URL?: string;
}

export const SCHEDULE_URL = "https://cdn.ntutbox.com/course/ops/season-schedule.json";
export const DISPATCH_URL =
  "https://api.github.com/repos/poterpan/ntutbox-course/actions/workflows/season.yml/dispatches";
const USER_AGENT = "ntutbox-season-scheduler";

// 保活（D19）：公開 repo 的排程 workflow 在 60 天沒有 repo 活動後會被 GitHub 自動停用。
// 每週一次呼叫 enable API（已啟用時也回 204、冪等），被停用最多一週就會自動恢復。
export const KEEPALIVE_WORKFLOWS = ["daily.yml", "weekly.yml"] as const;
export const enableUrl = (workflow: string) =>
  `https://api.github.com/repos/poterpan/ntutbox-course/actions/workflows/${workflow}/enable`;
/** 每週的保活整點：台北週一 00:00 ＝ UTC 週日 16:00。 */
export const KEEPALIVE_UTC_DAY = 0;
export const KEEPALIVE_UTC_HOUR = 16;
const HOUR_MS = 60 * 60 * 1000;

export interface Slot {
  at: string;
  terms: string;
  windows?: string[];
  reason?: string;
}

export interface Schedule {
  schema_version: 1;
  calendar_sha256?: string;
  slots: Slot[];
}

export interface RunOptions {
  /** 重試前等待毫秒數（測試用 0）。 */
  retryDelayMs?: number;
}

export type RunResult =
  | { status: "no-token" }
  | { status: "no-schedule" }
  | { status: "schedule-error" }
  | { status: "no-slot"; hour: string }
  | { status: "dispatched"; hour: string; terms: string[] }
  | { status: "dispatch-failed"; hour: string; terms: string[] };

/** 把排定時間截到整點。Cloudflare 可能晚幾分鐘才執行，但 scheduledTime 是「原定」時間，截整點即可。 */
export function truncateToHour(ms: number): number {
  return Math.floor(ms / HOUR_MS) * HOUR_MS;
}

/** 驗證排程表格式；不合格回傳錯誤訊息字串。 */
export function validateSchedule(data: unknown): Schedule | string {
  if (typeof data !== "object" || data === null) return "排程表不是 JSON 物件";
  const obj = data as Record<string, unknown>;
  if (obj.schema_version !== 1) return `不支援的 schema_version：${JSON.stringify(obj.schema_version)}`;
  if (!Array.isArray(obj.slots)) return "slots 不是陣列";
  for (const [i, slot] of obj.slots.entries()) {
    if (typeof slot !== "object" || slot === null) return `slots[${i}] 不是物件`;
    const s = slot as Record<string, unknown>;
    if (typeof s.at !== "string" || Number.isNaN(Date.parse(s.at))) return `slots[${i}].at 不是合法時間`;
    if (typeof s.terms !== "string" || s.terms.trim() === "") return `slots[${i}].terms 缺漏`;
  }
  return obj as unknown as Schedule;
}

/** 找出 `at` 與該整點為同一時刻的 slot（以 instant 比較，時區寫法不影響）。 */
export function findSlots(schedule: Schedule, hourMs: number): Slot[] {
  return schedule.slots.filter((s) => Date.parse(s.at) === hourMs);
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** 發請求；5xx 或網路錯誤重試一次。回傳最後一次的 Response，兩次都網路錯誤則拋出。 */
async function fetchWithRetry(
  url: string,
  init: RequestInit,
  label: string,
  retryDelayMs: number,
): Promise<Response> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const res = await fetch(url, init);
      if (res.status < 500 || attempt === 2) return res;
      console.warn(`[${label}] HTTP ${res.status}，${retryDelayMs}ms 後重試`);
    } catch (err) {
      lastError = err;
      if (attempt === 2) break;
      console.warn(`[${label}] 網路錯誤（${String(err)}），${retryDelayMs}ms 後重試`);
    }
    if (retryDelayMs > 0) await sleep(retryDelayMs);
  }
  throw lastError;
}

async function loadSchedule(retryDelayMs: number): Promise<Schedule | "missing" | "error"> {
  let res: Response;
  try {
    res = await fetchWithRetry(
      SCHEDULE_URL,
      { headers: { "User-Agent": USER_AGENT }, cache: "no-store" },
      "schedule",
      retryDelayMs,
    );
  } catch (err) {
    console.error(`[schedule] 讀取排程表失敗：${String(err)}`);
    return "error";
  }
  if (res.status === 404) {
    // Python 端尚未發佈排程表時是正常狀態，不算錯誤。
    console.log("[schedule] 排程表尚未發佈（404），本次不觸發");
    return "missing";
  }
  if (!res.ok) {
    console.error(`[schedule] 讀取排程表失敗：HTTP ${res.status} ${await safeText(res)}`);
    return "error";
  }
  let data: unknown;
  try {
    data = await res.json();
  } catch (err) {
    console.error(`[schedule] 排程表不是合法 JSON：${String(err)}`);
    return "error";
  }
  const result = validateSchedule(data);
  if (typeof result === "string") {
    console.error(`[schedule] 排程表格式錯誤：${result}`);
    return "error";
  }
  return result;
}

async function safeText(res: Response): Promise<string> {
  try {
    return (await res.text()).slice(0, 2000);
  } catch {
    return "";
  }
}

function githubHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": USER_AGENT,
  };
}

async function dispatch(terms: string, token: string, retryDelayMs: number): Promise<boolean> {
  const init: RequestInit = {
    method: "POST",
    headers: { ...githubHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs: { terms } }),
  };
  let res: Response;
  try {
    res = await fetchWithRetry(DISPATCH_URL, init, "dispatch", retryDelayMs);
  } catch (err) {
    console.error(`[dispatch] terms=${terms} 網路錯誤（已重試）：${String(err)}`);
    return false;
  }
  if (res.status !== 204) {
    console.error(`[dispatch] terms=${terms} 失敗：HTTP ${res.status} ${await safeText(res)}`);
    return false;
  }
  console.log(`[dispatch] 已觸發 season.yml，terms=${terms}`);
  return true;
}

/** 一次 cron 的完整流程；獨立匯出方便測試。 */
export async function run(scheduledTime: number, env: Env, opts: RunOptions = {}): Promise<RunResult> {
  const retryDelayMs = opts.retryDelayMs ?? 2000;
  const token = env.GITHUB_TOKEN;
  if (!token) {
    console.error("[config] 缺少 GITHUB_TOKEN secret（npx wrangler secret put GITHUB_TOKEN），本次不觸發");
    return { status: "no-token" };
  }

  const schedule = await loadSchedule(retryDelayMs);
  if (schedule === "missing") return { status: "no-schedule" };
  if (schedule === "error") return { status: "schedule-error" };

  const hourMs = truncateToHour(scheduledTime);
  const hour = new Date(hourMs).toISOString();
  const slots = findSlots(schedule, hourMs);
  if (slots.length === 0) {
    console.log(`[schedule] ${hour} 無排定 slot，不觸發`);
    return { status: "no-slot", hour };
  }

  // 正常一個整點只會有一個 slot；萬一有多個，每種 terms 各觸發一次（去重）。
  const terms = [...new Set(slots.map((s) => s.terms))];
  if (slots.length > 1) console.warn(`[schedule] ${hour} 有 ${slots.length} 個 slot，依 terms 去重後觸發 ${terms.length} 次`);
  for (const s of slots) {
    console.log(`[schedule] ${hour} 命中 slot：terms=${s.terms} reason=${s.reason ?? "-"} windows=${(s.windows ?? []).join("、")}`);
  }

  let ok = true;
  for (const t of terms) {
    if (!(await dispatch(t, token, retryDelayMs))) ok = false;
  }
  return ok ? { status: "dispatched", hour, terms } : { status: "dispatch-failed", hour, terms };
}

export type KeepaliveResult =
  | { status: "skipped" }
  | { status: "no-token" }
  | { status: "enabled"; workflows: string[] }
  | { status: "failed"; failed: string[] };

/** 截整點後是否為每週保活的整點（台北週一 00:00）。 */
export function isKeepaliveHour(hourMs: number): boolean {
  const d = new Date(hourMs);
  return d.getUTCDay() === KEEPALIVE_UTC_DAY && d.getUTCHours() === KEEPALIVE_UTC_HOUR;
}

async function enableWorkflow(workflow: string, token: string, retryDelayMs: number): Promise<boolean> {
  let res: Response;
  try {
    res = await fetchWithRetry(enableUrl(workflow), { method: "PUT", headers: githubHeaders(token) }, "keepalive", retryDelayMs);
  } catch (err) {
    console.error(`[keepalive] ${workflow} 網路錯誤（已重試）：${String(err)}`);
    return false;
  }
  if (res.status !== 204) {
    console.error(`[keepalive] ${workflow} enable 失敗：HTTP ${res.status} ${await safeText(res)}`);
    return false;
  }
  console.log(`[keepalive] ${workflow} enable → 204`);
  return true;
}

/** 每週保活：與 season slot 無關，只看整點。其他整點直接略過、不發請求。 */
export async function keepalive(scheduledTime: number, env: Env, opts: RunOptions = {}): Promise<KeepaliveResult> {
  if (!isKeepaliveHour(truncateToHour(scheduledTime))) return { status: "skipped" };
  const retryDelayMs = opts.retryDelayMs ?? 2000;
  const token = env.GITHUB_TOKEN;
  if (!token) {
    console.error("[keepalive] 缺少 GITHUB_TOKEN secret，本週無法保活 daily／weekly");
    return { status: "no-token" };
  }
  const failed: string[] = [];
  for (const wf of KEEPALIVE_WORKFLOWS) {
    if (!(await enableWorkflow(wf, token, retryDelayMs))) failed.push(wf);
  }
  return failed.length ? { status: "failed", failed } : { status: "enabled", workflows: [...KEEPALIVE_WORKFLOWS] };
}

// ------------------------------------------------------------------ web 自動重新部署（D22）
//
// `/browse/**` hub 是 build 期產生的靜態頁（apps/web/src/lib/hub/build-catalog.ts），
// 預設學期切換的那一刻若沒有重新 build，hub 會一直停在舊學期。manifest 的
// `term_schedule.default[].from` 是預設學期生效的時刻（Python 端從行事曆產出），
// 所以每小時看一次：這個整點就是某個 `from` 的生效整點 → POST Workers Builds Deploy Hook。
// 與 season slot、保活互不相干；缺 secret 或 manifest 沒有 term_schedule 都只是跳過。

export const MANIFEST_URL = "https://cdn.ntutbox.com/course/v1/manifest.json";

export interface TermScheduleEntry {
  term: string;
  from: string;
}

export type RedeployResult =
  | { status: "no-hook" }
  | { status: "no-term-schedule" }
  | { status: "manifest-error" }
  | { status: "no-switch"; hour: string }
  | { status: "triggered"; hour: string; terms: string[] }
  | { status: "trigger-failed"; hour: string; terms: string[] };

/**
 * `from` 對應的觸發整點：`from` 截到整點；若 `from` 不在整點上則取下一個整點
 * （cron 只在整點醒來，提早 build 會在切換前產出、hub 仍是舊學期）。
 * 整點上的 `from`（行事曆推導的都是）兩種算法相同。
 */
export function effectiveHour(fromMs: number): number {
  const h = truncateToHour(fromMs);
  return h === fromMs ? h : h + HOUR_MS;
}

/** 取出 manifest 的 `term_schedule.default`；缺欄位或形狀不對回傳 null（容忍另一邊尚未上線）。 */
export function defaultTermSchedule(manifest: unknown): TermScheduleEntry[] | null {
  if (typeof manifest !== "object" || manifest === null) return null;
  const ts = (manifest as Record<string, unknown>).term_schedule;
  if (typeof ts !== "object" || ts === null) return null;
  const def = (ts as Record<string, unknown>).default;
  if (!Array.isArray(def)) return null;
  return def.filter(
    (e): e is TermScheduleEntry =>
      typeof e === "object" &&
      e !== null &&
      typeof (e as Record<string, unknown>).term === "string" &&
      typeof (e as Record<string, unknown>).from === "string" &&
      !Number.isNaN(Date.parse((e as Record<string, unknown>).from as string)),
  );
}

/** 這個整點生效的預設學期切換（通常 0 或 1 筆）。 */
export function findSwitches(entries: TermScheduleEntry[], hourMs: number): TermScheduleEntry[] {
  return entries.filter((e) => effectiveHour(Date.parse(e.from)) === hourMs);
}

async function loadManifest(retryDelayMs: number): Promise<unknown | "error"> {
  let res: Response;
  try {
    res = await fetchWithRetry(
      MANIFEST_URL,
      { headers: { "User-Agent": USER_AGENT }, cache: "no-store" },
      "redeploy",
      retryDelayMs,
    );
  } catch (err) {
    console.error(`[redeploy] 讀取 manifest 失敗：${String(err)}`);
    return "error";
  }
  if (!res.ok) {
    console.error(`[redeploy] 讀取 manifest 失敗：HTTP ${res.status} ${await safeText(res)}`);
    return "error";
  }
  try {
    return await res.json();
  } catch (err) {
    console.error(`[redeploy] manifest 不是合法 JSON：${String(err)}`);
    return "error";
  }
}

/** 預設學期切換整點 → POST Deploy Hook（5xx／網路錯誤重試一次）。 */
export async function redeploy(scheduledTime: number, env: Env, opts: RunOptions = {}): Promise<RedeployResult> {
  const hook = env.DEPLOY_HOOK_URL;
  if (!hook) {
    console.log("[redeploy] no deploy hook, skip（未設 DEPLOY_HOOK_URL secret）");
    return { status: "no-hook" };
  }
  const retryDelayMs = opts.retryDelayMs ?? 2000;
  const manifest = await loadManifest(retryDelayMs);
  if (manifest === "error") return { status: "manifest-error" };
  const entries = defaultTermSchedule(manifest);
  if (entries === null) {
    console.log("[redeploy] manifest 沒有 term_schedule.default，skip");
    return { status: "no-term-schedule" };
  }

  const hourMs = truncateToHour(scheduledTime);
  const hour = new Date(hourMs).toISOString();
  const switches = findSwitches(entries, hourMs);
  if (switches.length === 0) return { status: "no-switch", hour };
  const terms = [...new Set(switches.map((s) => s.term))];
  console.log(`[redeploy] ${hour} 預設學期切換：${switches.map((s) => `${s.term}@${s.from}`).join("、")}`);

  let res: Response;
  try {
    // Deploy Hook 不需要 Authorization（URL 本身就是憑證）、不需要 body；回 200 + {success, result.build_uuid}。
    res = await fetchWithRetry(hook, { method: "POST", headers: { "User-Agent": USER_AGENT } }, "redeploy", retryDelayMs);
  } catch (err) {
    console.error(`[redeploy] Deploy Hook 網路錯誤（已重試）：${String(err)}`);
    return { status: "trigger-failed", hour, terms };
  }
  if (!res.ok) {
    // 不印 hook URL：它就是憑證。
    console.error(`[redeploy] Deploy Hook 失敗：HTTP ${res.status} ${await safeText(res)}`);
    return { status: "trigger-failed", hour, terms };
  }
  console.log(`[redeploy] 已觸發 web 重新部署：${await safeText(res)}`);
  return { status: "triggered", hour, terms };
}
