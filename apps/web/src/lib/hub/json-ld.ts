/**
 * JSON-LD 內嵌進 `<script>` 前的轉義。
 *
 * 為什麼需要：hub 頁的結構化資料含爬蟲來的字串（單位名、課名），不是程式常數。
 * 若哪天資料裡出現 `</script>`，`dangerouslySetInnerHTML` 會提前關閉標籤 → 注入。
 * 把 `<` 轉成 `\u003c` 是標準做法：JSON 語意完全不變，解析器照樣讀得到。
 * （layout.tsx 的 JSON_LD 是硬編常數所以沒這個風險；這裡不是。）
 */
export function jsonLdText(value: unknown): string {
  return JSON.stringify(value).replaceAll("<", "\\u003c").replaceAll("\u2028", "\\u2028").replaceAll("\u2029", "\\u2029");
}
