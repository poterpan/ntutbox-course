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
