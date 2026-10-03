import { describe, it, expect } from "vitest";
import robots from "@/app/robots";
import { AI_TRAINING_CRAWLERS, MUST_ALLOW_CRAWLERS } from "@/lib/seo/ai-crawlers";

describe("robots.txt AI policy (D26)", () => {
  const rules = robots().rules;
  const groups = Array.isArray(rules) ? rules : [rules];
  const disallowed = groups
    .filter((g) => g.disallow === "/")
    .flatMap((g) => (Array.isArray(g.userAgent) ? g.userAgent : [g.userAgent]));

  it("disallows AI training crawlers", () => {
    for (const bot of ["GPTBot", "ClaudeBot", "CCBot", "meta-externalagent", "Google-Extended"]) {
      expect(disallowed).toContain(bot);
    }
  });

  it("never disallows AI search, AI assistants or search engines", () => {
    const lower = disallowed.map((b) => String(b).toLowerCase());
    for (const bot of MUST_ALLOW_CRAWLERS) {
      expect(lower).not.toContain(bot.toLowerCase());
    }
  });

  it("keeps everything else allowed", () => {
    expect(groups.some((g) => g.userAgent === "*" && g.allow === "/")).toBe(true);
    expect(AI_TRAINING_CRAWLERS.length).toBe(new Set(AI_TRAINING_CRAWLERS).size);
  });
});
