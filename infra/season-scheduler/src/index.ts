// Worker entry：只匯出 handler（具名匯出會被 workerd 當成 handler 而啟動失敗），邏輯見 scheduler.ts。
import { run, type Env } from "./scheduler";

export default {
  async scheduled(controller: ScheduledController, env: Env): Promise<void> {
    const result = await run(controller.scheduledTime, env);
    // 真正的失敗丟出例外，讓 Cloudflare 的 Cron Events 標成失敗、方便在 dashboard 看到。
    // 404（尚未發佈）與無 slot 是正常狀態，不丟。
    if (result.status === "no-token" || result.status === "schedule-error" || result.status === "dispatch-failed") {
      throw new Error(`season-scheduler 失敗：${result.status}`);
    }
  },
} satisfies ExportedHandler<Env>;
