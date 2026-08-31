/** 課程分享連結的 <noscript> 內容：把課程事實直接寫進 HTML body。
 *
 * 為什麼需要：本站是 CSR 單頁應用，不執行 JS 時 body 只有「沒有符合的課程」的
 * 空殼——2,461 個課程 URL 的 body 逐位元組相同。GPTBot / ClaudeBot /
 * PerplexityBot 等 AI 爬蟲都不渲染 JS，等於完全讀不到課綱。
 *
 * 為什麼用 noscript 而非直接注入 body：React 掛載在 body 上，直接注入會造成
 * hydration mismatch。noscript 不在 React 樹內，對 hydration 完全無影響。
 *
 * ⚠️ 這不是 cloaking：內容與 JS 渲染後使用者看到的一致（同一份 course JSON），
 * 只是換一種呈現。若日後改動，務必維持「兩者內容一致」這個前提。
 *
 * Cloudflare-free，vitest 可測；worker/index.ts 負責抓資料與注入。
 */

export interface CourseDetail {
  name?: { zh?: string | null; en?: string | null } | null;
  course_code?: string | null;
  offering_id?: string | null;
  description?: { zh?: string | null; en?: string | null } | null;
  syllabi?: Array<{
    teacher_name?: string | null;
    outline?: string | null;
    assessment?: string | null;
    materials?: string | null;
    updated_at?: string | null;
  } | null> | null;
}

/** 目錄端的開課資訊（教師/時段/教室/學分），與 detail 互補。 */
export interface CourseCatalogInfo {
  credits?: string | number | null;
  unit_name?: string | null;
  teachers?: Array<{ name?: string | null } | null> | null;
  classrooms?: Array<{ name?: string | null } | null> | null;
}

function esc(s: string): string {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/** 長文截斷：AI 爬蟲要的是可引用的事實，不是整份課綱；也避免 HTML 過度膨脹。 */
function clip(s: string, max: number): string {
  const t = s.replace(/\s+/g, " ").trim();
  return t.length <= max ? t : `${t.slice(0, max)}…`;
}

function section(label: string, value: string | null | undefined, max = 600): string {
  if (!value || !value.trim()) return "";
  return `<h3>${esc(label)}</h3><p>${esc(clip(value, max))}</p>`;
}

/**
 * @param termKey 學期（如 "115-1"）
 * @returns noscript 內部的 HTML；資料不足以構成有意義的內容時回 null（不輸出空殼）
 */
export function buildCourseNoscriptHtml(
  detail: CourseDetail,
  termKey: string,
  catalog?: CourseCatalogInfo | null,
): string | null {
  const name = detail.name?.zh;
  if (!name) return null;

  const syl = (detail.syllabi ?? []).find((s) => s && (s.outline || s.assessment || s.materials));
  const teachers = (catalog?.teachers ?? [])
    .map((t) => t?.name)
    .filter((n): n is string => !!n);
  const teacherName = teachers.join("、") || syl?.teacher_name || "";
  const rooms = (catalog?.classrooms ?? []).map((r) => r?.name).filter((n): n is string => !!n);

  const facts: string[] = [];
  if (teacherName) facts.push(`授課教師：${teacherName}`);
  if (catalog?.unit_name) facts.push(`開課單位：${catalog.unit_name}`);
  if (catalog?.credits != null) facts.push(`學分：${catalog.credits}`);
  if (rooms.length) facts.push(`教室：${rooms.join("、")}`);
  if (detail.course_code) facts.push(`課程編碼：${detail.course_code}`);
  if (detail.offering_id) facts.push(`課號：${detail.offering_id}`);

  const parts = [
    `<h1>${esc(name)}${detail.name?.en ? `（${esc(detail.name.en)}）` : ""}</h1>`,
    `<p>${esc(termKey)} 學期・國立臺北科技大學</p>`,
    facts.length ? `<ul>${facts.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : "",
    section("課程概述", detail.description?.zh),
    section("教學大綱", syl?.outline, 900),
    section("評量方式", syl?.assessment),
    section("教材與參考書", syl?.materials, 400),
    // 誠實揭露：這是非官方整理，且此區塊是無 JS 時的替代呈現。
    `<p>資料整理自國立臺北科技大學公開課程資訊。本站為非官方工具，正式選課以學校系統為準。</p>`,
  ].filter(Boolean);

  return parts.join("");
}
