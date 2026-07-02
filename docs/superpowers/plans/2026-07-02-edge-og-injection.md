# 分享連結課名 OG（邊緣注入）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分享連結（`?course=` / `?plan=`）貼到社群時，OG 標題/描述顯示實際課名（`?course`）或「分享的課表 · N 門課」（`?plan`）。

**Architecture:** cron 產物新增小索引 `terms/{term}/names.json`（課號→課名）；web 由 assets-only 改成 Worker + ASSETS binding，帶 `?course/?plan` 的 `/` 請求以 HTMLRewriter 改寫 OG meta，其餘原樣 `env.ASSETS.fetch`。

**Tech Stack:** Cloudflare Workers（web，加 worker script + ASSETS binding + HTMLRewriter）、Python（crawler artifacts / infra publish）、TypeScript、vitest。

## Global Constraints

- **不改爬蟲抓取邏輯**；`names.json` 只在既有 artifact 產生處（`build_v1`）從 catalog 導出。
- **邊緣不可壞頁**：term/names 缺、404、課號不在、fetch/parse 失敗 → 一律 fallback 原樣回 SPA（維持既有通用 OG）。
- **非分享請求 100% 原樣** `env.ASSETS.fetch`（含所有靜態資源與 SPA fallback）。
- HTMLRewriter 只改既有 meta 的 `content`，不新增/刪節點。selectors（已確認）：`meta[property="og:title"]`、`meta[property="og:description"]`、`meta[name="twitter:title"]`、`meta[name="twitter:description"]`。
- OG 文案：`?course` → title=`{課名}｜北科盒子 排課`、desc=`在北科盒子 排課查看課程詳情、加入你的課表`；`?plan`（n=id 數）→ title=`分享的課表 · {n} 門課｜北科盒子 排課`、desc=`查看這份 {n} 門課的課表規劃`。
- `DATA_BASE_URL`（prod）= `https://cdn.ntutbox.com/course/v1`。
- **上線順序**：Task 1 落地並 publish（names.json 上 cdn）後，Task 3 的 worker 才在 prod 顯示得出課名。Task 3 邏輯先用本地/fixtures 驗。
- 指令：crawler 在 `crawler/`（pytest）；web 在 `apps/web/`（`npm run lint/test/build`、`npx wrangler`）。

---

### Task 1: 產物與發佈 `names.json`（crawler + infra + fixtures）

**Files:**
- Modify: `crawler/ntut_catalog/artifacts.py`（`build_v1`，寫 catalog.json 後導出 names.json）
- Test: `crawler/tests/test_artifacts.py`（新增 names.json 產出測試）
- Modify: `infra/publish.py`（預設上傳清單加 `names.json`）
- Create: `apps/web/public/data/v1/terms/*/names.json`（由既有 catalog fixtures 導出）

**Interfaces:**
- Produces: 每學期 `data/v1/terms/{term}/names.json`，內容 `{ "<offering_id>": "<name.zh>" }`（只收有 zh 課名者）。

- [ ] **Step 1: 讀既有 build_v1 測試設定**

Run: `sed -n '1,60p' crawler/tests/test_artifacts.py`
目的：沿用其建立 canonical → 呼叫 `build_v1` 的既有 fixture 寫法（下一步的測試要接同一套 setup）。

- [ ] **Step 2: 在 test_artifacts.py 新增失敗測試**

沿用既有 build_v1 測試的 setup（同 out_dir / canonical 建法），新增：

```python
def test_build_v1_writes_names_index(tmp_path):
    # 沿用本檔既有 helper 建立含一課的 canonical（course 名為「資料結構」），再：
    from ntut_catalog.artifacts import build_v1
    build_v1(tmp_path, generated_at="2026-07-02T00:00:00Z")
    import json
    names_files = list(tmp_path.glob("v1/terms/*/names.json"))
    assert names_files, "names.json 應被產出"
    names = json.loads(names_files[0].read_text(encoding="utf-8"))
    assert isinstance(names, dict) and len(names) >= 1
    # 值為中文課名、鍵為課號字串
    assert any(v == "資料結構" for v in names.values())
```
（若既有測試已有建 canonical 的 helper/fixture，直接重用；課名字串對齊該 helper 建的課。）

- [ ] **Step 3: 跑測試，確認失敗**

Run: `cd crawler && python -m pytest tests/test_artifacts.py::test_build_v1_writes_names_index -q`
Expected: FAIL（names.json 尚未產出）。

- [ ] **Step 4: 在 build_v1 導出 names.json**

`crawler/ntut_catalog/artifacts.py`，在 `(v1 / "catalog.json").write_text(...)` 之後緊接：

```python
        # names 索引（邊緣 OG 用；課號→中文課名，小檔、隨 cron 自動發）
        names = {c.offering_id: c.name.zh for c in courses if c.name and c.name.zh}
        (v1 / "names.json").write_text(
            json.dumps(names, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
```

- [ ] **Step 5: 跑測試，確認通過 + 全 crawler 測試綠**

Run: `cd crawler && python -m pytest tests/test_artifacts.py -q && python -m pytest -q`
Expected: PASS（新測試 + 既有全綠）。

- [ ] **Step 6: publish.py 上傳清單加 names.json**

`infra/publish.py` `_v1_files_for` 內的固定清單：
```python
        for name in ["catalog.json", "classes.json", "periods.json", "enrollment.json", "mprograms.json"]:
```
改為（加 `names.json`）：
```python
        for name in ["catalog.json", "classes.json", "periods.json", "enrollment.json", "mprograms.json", "names.json"]:
```
若 `infra` 有測試（`crawler/tests/test_publish.py`）跑一次確認沒壞：`cd crawler && python -m pytest tests/test_publish.py -q`。

- [ ] **Step 7: 產生 fixtures 的 names.json（本地/worker 測試要用）**

Run:
```bash
cd apps/web/public/data/v1/terms && for d in */; do python3 -c "import json; c=json.load(open('${d}catalog.json'))['courses']; json.dump({x['offering_id']:x['name']['zh'] for x in c if x.get('name',{}).get('zh')}, open('${d}names.json','w'), ensure_ascii=False, separators=(',',':'))"; done && ls */names.json
```
Expected: 每個 term 目錄出現 `names.json`。抽查：`python3 -c "import json; d=json.load(open('115-1/names.json')); print(len(d), d.get('360744'))"` → 應印出數量與「國文」。

- [ ] **Step 8: Commit**

```bash
git add crawler/ntut_catalog/artifacts.py crawler/tests/test_artifacts.py infra/publish.py apps/web/public/data/v1
git commit -m "feat(data): #30 產出並發佈 names.json 課名索引（邊緣 OG 用）"
```

---

### Task 2: 純 OG 解析邏輯 + 單元測試（web）

**Files:**
- Create: `apps/web/src/lib/share/og.ts`
- Test: `apps/web/src/lib/share/og.test.ts`

**Interfaces:**
- Produces:
  - `planCount(plan: string): number` — `"a.b.c"` → 3；空/雜訊過濾。
  - `resolveShareOg(params: URLSearchParams, names: Record<string,string> | null): { title: string; description: string } | null` — 依 `course`/`plan` 決定 OG；`course` 但 names 查無 → `null`；皆無 → `null`。

- [ ] **Step 1: 寫失敗測試 `og.test.ts`**

```ts
import { describe, it, expect } from "vitest";
import { planCount, resolveShareOg } from "./og";

describe("planCount", () => {
  it("counts dot-separated ids, ignoring blanks", () => {
    expect(planCount("360744.361278.360753")).toBe(3);
    expect(planCount("")).toBe(0);
    expect(planCount("360744..")).toBe(1);
  });
});

describe("resolveShareOg", () => {
  const names = { "360744": "國文" };
  it("course → course name title when found", () => {
    const og = resolveShareOg(new URLSearchParams("term=115-1&course=360744"), names);
    expect(og).toEqual({ title: "國文｜北科盒子 排課", description: "在北科盒子 排課查看課程詳情、加入你的課表" });
  });
  it("course not in names → null (fallback)", () => {
    expect(resolveShareOg(new URLSearchParams("term=115-1&course=999999"), names)).toBeNull();
  });
  it("plan → count-based title", () => {
    const og = resolveShareOg(new URLSearchParams("term=115-1&plan=360744.361278"), null);
    expect(og).toEqual({ title: "分享的課表 · 2 門課｜北科盒子 排課", description: "查看這份 2 門課的課表規劃" });
  });
  it("no share params → null", () => {
    expect(resolveShareOg(new URLSearchParams(""), null)).toBeNull();
  });
});
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd apps/web && npx vitest run src/lib/share/og.test.ts`
Expected: FAIL（`./og` 不存在）。

- [ ] **Step 3: 實作 `og.ts`**

```ts
/** Pure share-link OG resolution. Kept CF-free so it unit-tests in vitest;
 * worker/index.ts wires the network (names.json) + HTMLRewriter around it. */
export function planCount(plan: string): number {
  return plan.split(".").filter(Boolean).length;
}

export function resolveShareOg(
  params: URLSearchParams,
  names: Record<string, string> | null,
): { title: string; description: string } | null {
  const course = params.get("course");
  if (course) {
    const name = names?.[course];
    if (!name) return null;
    return { title: `${name}｜北科盒子 排課`, description: "在北科盒子 排課查看課程詳情、加入你的課表" };
  }
  const plan = params.get("plan");
  if (plan) {
    const n = planCount(plan);
    if (n < 1) return null;
    return { title: `分享的課表 · ${n} 門課｜北科盒子 排課`, description: `查看這份 ${n} 門課的課表規劃` };
  }
  return null;
}
```

- [ ] **Step 4: 跑測試，確認通過**

Run: `cd apps/web && npx vitest run src/lib/share/og.test.ts && npm test`
Expected: 新測試 PASS；全測試（原 109 + 新）綠。

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/share/og.ts apps/web/src/lib/share/og.test.ts
git commit -m "feat(web): #30 純 OG 解析（resolveShareOg / planCount）+ 測試"
```

---

### Task 3: web 轉 Worker + ASSETS + HTMLRewriter 注入

**Files:**
- Modify: `apps/web/wrangler.jsonc`（assets-only → main + assets.binding + vars）
- Create: `apps/web/worker/index.ts`
- Modify: `apps/web/package.json`（devDep `@cloudflare/workers-types`）

**Interfaces:**
- Consumes: `resolveShareOg`（Task 2）；`names.json`（Task 1，經 `DATA_BASE_URL`）。

- [ ] **Step 1: 加 worker 型別 devDep**

Run: `cd apps/web && npm i -D @cloudflare/workers-types`

- [ ] **Step 2: 改 `wrangler.jsonc`**

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "ntutbox-course-web",
  "compatibility_date": "2025-06-05",
  "main": "worker/index.ts",
  "assets": {
    "directory": "./out",
    "binding": "ASSETS",
    "not_found_handling": "single-page-application"
  },
  "vars": {
    "DATA_BASE_URL": "https://cdn.ntutbox.com/course/v1"
  }
}
```

- [ ] **Step 3: 建 `apps/web/worker/index.ts`**

```ts
/// <reference types="@cloudflare/workers-types" />
import { resolveShareOg } from "../src/lib/share/og";

interface Env {
  ASSETS: Fetcher;
  DATA_BASE_URL: string;
}

// Best-effort per-isolate cache: term → names map. Fresh isolates re-fetch;
// new terms use a new key so nothing needs manual invalidation.
const namesCache = new Map<string, Record<string, string>>();

async function getNames(term: string, base: string): Promise<Record<string, string>> {
  const cached = namesCache.get(term);
  if (cached) return cached;
  const res = await fetch(`${base}/terms/${term}/names.json`, {
    cf: { cacheTtl: 3600, cacheEverything: true },
  });
  if (!res.ok) throw new Error(`names ${res.status}`);
  const names = (await res.json()) as Record<string, string>;
  namesCache.set(term, names);
  return names;
}

class SetContent {
  constructor(private content: string) {}
  element(el: Element) {
    el.setAttribute("content", this.content);
  }
}

export default {
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
```

- [ ] **Step 4: 型別 + lint + build**

Run: `cd apps/web && npx tsc --noEmit && npm run lint && npm run build`
Expected: 全綠。（`build` 產出 `./out`；wrangler 部署時才打包 worker。）
若 tsc 因 worker 型別衝突報錯：確認 `worker/index.ts` 頂端有 `/// <reference types="@cloudflare/workers-types" />`；必要時在 tsconfig `exclude` 之外、以該檔的 reference 為準（不要把 workers-types 加進全域 `types`，以免污染 Next app DOM 型別）。

- [ ] **Step 5: 本地驗證（wrangler dev + curl）**

先讓 fixtures 的 names.json 可被 worker 抓到：開一個靜態伺服器服務 fixtures，或直接指 `DATA_BASE_URL` 到本地。做法：

```bash
cd apps/web
# 終端 A：服務 fixtures 當 data base（含 Task 1 產的 names.json）
npx serve public/data/v1 -l 8788 -C   # 或任一靜態 server；-C 開 CORS（worker 端 fetch 不需 CORS，但方便）
# 終端 B：以本地 data base 跑 worker（覆寫 var）
npx wrangler dev --var DATA_BASE_URL:http://localhost:8788
```
驗證（終端 C）：
```bash
# 單堂：og:title 應被改成課名
curl -s "http://localhost:8787/?term=115-1&course=360744" | grep -oE '<meta property="og:title"[^>]*>'
# 期望 content="國文｜北科盒子 排課"
# 整份：
curl -s "http://localhost:8787/?term=115-1&plan=360744.361278" | grep -oE '<meta property="og:title"[^>]*>'
# 期望 content="分享的課表 · 2 門課｜北科盒子 排課"
# 無參數：原樣通用值
curl -s "http://localhost:8787/" | grep -oE '<meta property="og:title"[^>]*>'
# 期望 content="北科盒子 · 排課"
# 靜態資源仍正常（任一 /_next/... 200）
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8787/favicon.ico"
```
（`wrangler dev` port 預設 8787；serve port 8788。實際 port 以輸出為準。）

- [ ] **Step 6: Commit**

```bash
git add apps/web/wrangler.jsonc apps/web/worker/index.ts apps/web/package.json apps/web/package-lock.json
git commit -m "feat(web): #30 邊緣 Worker 注入分享連結課名 OG（HTMLRewriter）"
```

---

### 上線與真機驗收（非程式步驟，供收尾）

- **順序**：Task 1 合併並跑一次 `infra/publish.py`（或等 cron）→ `names.json` 上 `cdn.ntutbox.com/course/v1/terms/*/`。**再**部署 web worker（Task 2+3）。
- **真機 unfurl**：`names.json` 上 cdn 後，於 preview / prod 把 `course.ntutbox.com/?term=115-1&course=360744` 貼進 LINE / iMessage，確認預覽卡標題出現課名。（使用者執行；無法只靠截圖。）

## Self-Review

- **Spec coverage**：names.json 產出（T1 S4）+ 發佈（T1 S6）+ fixtures（T1 S7）；`?course`/`?plan` OG（T2 resolveShareOg）；worker 注入 + 非分享原樣 + fallback（T3 S3）；assets→worker 轉換（T3 S2）；本地驗證（T3 S5）；上線順序（末段）。皆覆蓋。
- **Placeholder scan**：T1 S2 測試依賴「既有 build_v1 測試 setup」——已於 S1 先讀該檔對齊，非佔位；其餘皆完整程式碼。
- **Type consistency**：`resolveShareOg(params, names)` / `planCount(plan)` 簽章在 T2 定義、T3 worker 一致使用；`Record<string,string>` names 型別一致；`Env.DATA_BASE_URL` 與 wrangler `vars` 對齊。
- **風險**：T3 S4 註記 worker 型別不污染 Next 全域；T3 S3 全程 try/catch fallback 不壞頁。
