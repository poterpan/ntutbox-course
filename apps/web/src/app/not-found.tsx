import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "找不到頁面",
  robots: { index: false },
};

// 靜態輸出成 out/404.html；Cloudflare assets 以 404 狀態碼回應未知路徑
// （wrangler.jsonc not_found_handling: "404-page"），避免整站被當 soft-404。
export default function NotFound() {
  return (
    <main className="flex h-dvh items-center justify-center p-6">
      <div className="glass-surface max-w-md rounded-2xl p-8 text-center">
        <p className="text-5xl font-bold tracking-tight text-[var(--ink)]">404</p>
        <h1 className="mt-3 text-lg font-semibold text-[var(--ink)]">找不到這個頁面</h1>
        <p className="mt-2 text-sm text-[var(--ink-soft)]">網址可能打錯了，或這個內容已不存在。</p>
        <Link
          href="/"
          className="mt-6 inline-block rounded-xl bg-[var(--accent)] px-5 py-2.5 text-sm font-semibold text-white"
        >
          回到排課首頁
        </Link>
      </div>
    </main>
  );
}
