/** AI 訓練用爬蟲的 robots.txt token（D26）。
 *
 * 只放「收集內容去訓練模型」的爬蟲。AI 搜尋與助理（OAI-SearchBot、ChatGPT-User、
 * Claude-SearchBot、Claude-User、PerplexityBot、Perplexity-User）和搜尋引擎（Googlebot、
 * bingbot、Applebot）**不可**加進來：使用者問 AI 北科的事時要能搜尋到本站並附連結。
 *
 * 實際阻擋在 Cloudflare WAF「course: block AI training crawlers」（ntutbox-edge
 * docs/zone-topology.md）。Google-Extended、Applebot-Extended 沒有獨立爬蟲，只能在這裡宣告。
 */
export const AI_TRAINING_CRAWLERS = [
  "GPTBot",
  "ClaudeBot",
  "anthropic-ai",
  "CCBot",
  "Bytespider",
  "meta-externalagent",
  "Amazonbot",
  "Google-Extended",
  "Applebot-Extended",
  "cohere-ai",
  "cohere-training-data-crawler",
  "Diffbot",
  "AI2Bot",
  "Omgilibot",
  "Timpibot",
  "ImagesiftBot",
] as const;

/** 必須能讀本站的 AI 搜尋／助理與搜尋引擎；測試用來防止誤加進上面的清單。 */
export const MUST_ALLOW_CRAWLERS = [
  "OAI-SearchBot",
  "ChatGPT-User",
  "Claude-SearchBot",
  "Claude-User",
  "PerplexityBot",
  "Perplexity-User",
  "Googlebot",
  "bingbot",
  "Applebot",
] as const;
