// 分享/複製：手機優先原生分享面板，否則複製到剪貼簿，再否則交由 UI 提示手動複製。

export type ShareResult = "shared" | "copied" | "failed";

export async function shareOrCopy(url: string, title: string): Promise<ShareResult> {
  if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
    try {
      await navigator.share({ title, url });
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
