// 分享/複製：觸控裝置（手機/平板）用原生分享面板，桌面一律複製連結，再否則交由 UI 提示手動複製。

export type ShareResult = "shared" | "copied" | "failed";

/** 只有以觸控為主的裝置才用原生分享面板；桌面（含有 navigator.share 的 Mac Chrome/Safari）一律複製，保持一致。 */
function prefersNativeShare(): boolean {
  if (typeof navigator === "undefined" || typeof navigator.share !== "function") return false;
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
  return window.matchMedia("(hover: none) and (pointer: coarse)").matches;
}

export async function shareOrCopy(url: string, title: string, text?: string): Promise<ShareResult> {
  if (prefersNativeShare()) {
    try {
      // text 帶課名 → 傳到聊天室時即使無連結預覽也看得到是哪門課。
      await navigator.share({ title, url, ...(text ? { text } : {}) });
      return "shared";
    } catch (e) {
      // 使用者取消分享面板 → 不算失敗、不提示。
      if (e instanceof Error && e.name === "AbortError") return "shared";
      // 其他錯誤 → 退回複製。
    }
  }
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(url);
      return "copied";
    } catch {
      // 落到失敗提示。
    }
  }
  return "failed";
}
