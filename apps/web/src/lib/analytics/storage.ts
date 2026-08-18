// sessionStorage 讀寫的安全包裝：Safari 私密瀏覽／存滿／SSR 都會讓 sessionStorage 丟例外，
// 而分析永遠不能讓產品操作爆掉 → 存不進去就退回 process 內的 Map（同一次載入仍有 guard 效果）。

const memory = new Map<string, string>();

export function readSession(key: string): string | null {
  try {
    if (typeof window !== "undefined" && window.sessionStorage) {
      const v = window.sessionStorage.getItem(key);
      if (v !== null) return v;
    }
  } catch {
    // 落到 memory fallback
  }
  return memory.get(key) ?? null;
}

export function writeSession(key: string, value: string): void {
  memory.set(key, value);
  try {
    window.sessionStorage?.setItem(key, value);
  } catch {
    // memory 已記下，忽略
  }
}

/** 測試用：清掉 memory fallback（sessionStorage 由測試自己清）。 */
export function resetSessionFallback(): void {
  memory.clear();
}
