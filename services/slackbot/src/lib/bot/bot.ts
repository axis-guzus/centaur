import * as crypto from "node:crypto";
import { Chat } from "chat";
import { createSlackAdapter, type SlackAdapter } from "@chat-adapter/slack";
import { createPostgresState } from "@chat-adapter/state-pg";
import { normalizeThreadKey, splitThreadKey } from "@centaur/harness-events";
import { Pool } from "pg";
import { log } from "@/lib/logger";
import { API_URL, resilientFetch } from "./api-client";
import { postContextMessage } from "./harness";
import { handleMessage } from "./stream-turn";

let _pool: Pool | null = null;
function getPool(): Pool {
  if (!_pool) {
    _pool = new Pool({ connectionString: process.env.DATABASE_URL, max: 10 });
  }
  return _pool;
}

const SLACK_BOT_USERNAME = process.env.SLACK_BOT_USERNAME || "ai-agent";

export function getSlackBootstrapState(): { ready: boolean; missingEnvKeys: string[] } {
  const required = ["SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET"] as const;
  const missingEnvKeys = required.filter((k) => !process.env[k]?.trim());
  return { ready: missingEnvKeys.length === 0, missingEnvKeys: [...missingEnvKeys] };
}

function messageIdentifier(message: { ts?: string; userId?: string; text?: string; threadId?: string }): string {
  const ts = String(message.ts || "").trim();
  if (ts) return ts;
  return crypto.createHash("sha1").update(`${message.threadId || ""}:${message.userId || ""}:${message.text || ""}`).digest("hex");
}

function createBot() {
  const hasSlackCreds = Boolean(process.env.SLACK_BOT_TOKEN && process.env.SLACK_SIGNING_SECRET);

  const bot = new Chat({
    userName: SLACK_BOT_USERNAME,
    adapters: hasSlackCreds ? { slack: createSlackAdapter() } : {},
    state: createPostgresState({ client: getPool() }),
    onLockConflict: "force",
  } as ConstructorParameters<typeof Chat>[0]);

  // ── Mentions ────────────────────────────────────────────────────────────

  bot.onNewMention(async (thread, message) => {
    if (message.author.isMe || message.author.isBot) return;
    await thread.subscribe();

    let attachments = message.attachments ? [...message.attachments] : [];
    const mentionTs = (message as { ts?: string }).ts || "";

    if (attachments.length === 0 && mentionTs) {
      try {
        const slack = bot.getAdapter("slack") as SlackAdapter;
        const refetched = await slack.fetchMessage(thread.id, mentionTs);
        if (refetched?.attachments?.length) {
          attachments = [...refetched.attachments];
          log.info("mention_files_refetched", { thread: thread.id, count: attachments.length });
        }
      } catch (err) {
        log.warn("mention_files_refetch_failed", {
          thread: thread.id,
          error: err instanceof Error ? err.message : String(err),
        });
      }
    }

    await handleMessage(bot, thread, message.text, true, attachments, message.author.userId, mentionTs);
  });

  // ── Subscribed messages ─────────────────────────────────────────────────

  bot.onSubscribedMessage(async (thread, message) => {
    if (message.author.isMe || message.author.isBot) return;

    if (message.isMention) {
      const subTs = (message as { ts?: string }).ts || "";
      await handleMessage(bot, thread, message.text, false, message.attachments || [], message.author.userId, subTs);
      return;
    }

    const text = (message.text || "").trim();
    const threadKey = normalizeThreadKey(thread.id);
    const rawAttachments = message.attachments || [];
    const files = rawAttachments
      .filter((a) => !!a.url && !!a.name)
      .map((a) => ({ url: a.url!, name: a.name!, mimeType: a.mimeType }));
    if (!text && files.length === 0) return;

    const mid = messageIdentifier({
      ts: (message as { ts?: string }).ts || (message as { id?: string }).id,
      userId: message.author.userId,
      text,
      threadId: thread.id,
    });
    const slackTs = (message as { ts?: string }).ts || "";

    try {
      await postContextMessage(threadKey, text || "Shared attachment in thread.", {
        source: "slack_subscribed_message",
        userId: message.author.userId,
        messageId: mid,
        slackTs,
        attachments: files.length > 0 ? files : undefined,
      });
    } catch (error) {
      log.warn("thread_context_post_failed", {
        thread: threadKey,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  });

  // ── Orphan recovery ─────────────────────────────────────────────────────

  async function checkOrphanedCompletions() {
    if (!hasSlackCreds) return;
    try {
      const res = await resilientFetch(`${API_URL}/agent/orphaned?max_age_s=300`, {
        timeoutMs: 10_000,
        maxAttempts: 1,
      });
      if (!res.ok) return;
      const orphans = (await res.json()) as Array<{ thread_key: string; text: string; updated_at: string | null }>;
      if (orphans.length === 0) return;
      log.info("orphan_check_found", { count: orphans.length });

      const slack = bot.getAdapter("slack") as SlackAdapter;

      for (const orphan of orphans) {
        if (!orphan.text) continue;
        let channel: string, threadTs: string;
        try {
          ({ channel, threadTs } = splitThreadKey(orphan.thread_key));
        } catch {
          continue;
        }
        if (!/^[CDG]/.test(channel)) continue;

        try {
          const claimRes = await resilientFetch(`${API_URL}/agent/claim-delivery`, {
            method: "POST",
            body: JSON.stringify({ thread_key: orphan.thread_key }),
            maxAttempts: 1,
          });
          if (!claimRes.ok) continue;
          const { claimed } = (await claimRes.json()) as { claimed: boolean };
          if (!claimed) continue;
        } catch {
          continue;
        }

        try {
          await slack.postMessage(`slack:${channel}:${threadTs}`, orphan.text);
          log.info("orphan_delivered", { thread_key: orphan.thread_key });
          await resilientFetch(`${API_URL}/agent/mark-delivered`, {
            method: "POST",
            body: JSON.stringify({ thread_key: orphan.thread_key }),
          });
        } catch (err) {
          log.warn("orphan_delivery_failed", {
            thread_key: orphan.thread_key,
            error: err instanceof Error ? err.message : String(err),
          });
        }
      }
    } catch (err) {
      log.warn("orphan_check_failed", { error: err instanceof Error ? err.message : String(err) });
    }
  }

  setTimeout(checkOrphanedCompletions, 10_000);
  setInterval(checkOrphanedCompletions, 60_000);

  return bot;
}

let _bot: ReturnType<typeof createBot> | null = null;
export function getBot() {
  if (!_bot) _bot = createBot();
  return _bot;
}
