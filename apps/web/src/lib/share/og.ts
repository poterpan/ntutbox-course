/** Pure share-link OG resolution. Kept Cloudflare-free so it unit-tests in vitest;
 * worker/index.ts wires the network (names.json fetch) + HTMLRewriter around it. */
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
    return {
      title: `${name}｜北科盒子 排課`,
      description: "在北科盒子 排課查看課程詳情、加入你的課表",
    };
  }
  const plan = params.get("plan");
  if (plan) {
    const n = planCount(plan);
    if (n < 1) return null;
    return {
      title: `分享的課表 · ${n} 門課｜北科盒子 排課`,
      description: `查看這份 ${n} 門課的課表規劃`,
    };
  }
  return null;
}
