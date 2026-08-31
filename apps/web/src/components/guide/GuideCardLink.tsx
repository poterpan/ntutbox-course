import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { GlassCard } from "@/components/glass/GlassCard";
import { guidePath, type GuidePageMeta } from "@/lib/guide/pages";

/**
 * hub 與頁尾「其他指南」共用的卡片連結。
 *
 * 走站內 <Link>（trailingSlash: true，所以 href 一律帶結尾斜線，由 guidePath() 產）。
 * icon 一律用 lucide，不手刻 SVG。
 */
export function GuideCardLink({ page }: { page: GuidePageMeta }) {
  return (
    <GlassCard className="p-0">
      <Link
        href={guidePath(page.slug)}
        className="block rounded-xl p-4 transition-colors hover:bg-[var(--accent)]/8"
      >
        <p className="flex items-start gap-2 text-sm font-semibold text-[var(--ink)]">
          <span className="flex-1">{page.heading}</span>
          <ArrowRight className="mt-0.5 size-4 shrink-0 text-[var(--accent)]" aria-hidden />
        </p>
        <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--ink-soft)]">{page.answers}</p>
      </Link>
    </GlassCard>
  );
}
