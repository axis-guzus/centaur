/**
 * Next.js instrumentation hook — runs once at server startup.
 *
 * Eagerly initializes the Bolt-backed Slack app so the adapter is ready
 * before any webhooks arrive. Without this, the first webhook after
 * a deploy can hit the slackbot before the app is initialized,
 * returning 404/503 and losing the message.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    if (process.env.LMNR_PROJECT_API_KEY) {
      const { Laminar } = await import("@lmnr-ai/lmnr");
      Laminar.initialize({
        projectApiKey: process.env.LMNR_PROJECT_API_KEY,
        baseUrl: process.env.LMNR_BASE_URL,
        httpPort: process.env.LMNR_HTTP_PORT ? Number(process.env.LMNR_HTTP_PORT) : undefined,
        grpcPort: process.env.LMNR_GRPC_PORT ? Number(process.env.LMNR_GRPC_PORT) : undefined,
        metadata: {
          service: "slackbot",
          environment: process.env.CENTAUR_ENVIRONMENT || "local",
        },
      });
    }
    const { ensureBotReady, getSlackBootstrapState } = await import("@/lib/bot/setup");
    const { log } = await import("@/lib/logger");
    const bootstrap = getSlackBootstrapState();
    if (!bootstrap.ready) {
      log.warn("slackbot_startup_initialize_skipped", {
        missing_env_keys: bootstrap.missingEnvKeys,
        invalid_env_keys: bootstrap.invalidEnvKeys,
      });
      return;
    }
    void ensureBotReady().catch((error) => {
      log.error("slackbot_startup_initialize_failed", {
        error: error instanceof Error ? error.message : String(error),
      });
    });
  }
}
