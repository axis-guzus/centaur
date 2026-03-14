import { normalizeThreadKey, splitThreadKey } from "@centaur/harness-events";
import { CentaurClient } from "@centaur/api-client";
import type { InputContentBlock } from "@centaur/api-client";

import { log } from "@/lib/logger";
import { ProgressTracker } from "./progress-tracker";

// ── Types ─────────────────────────────────────────────────────────────────

export interface BotThread {
  id: string;
  subscribe(): Promise<void>;
  post(content: { markdown: string }): Promise<{ id: string; edit(content: { markdown: string }): Promise<void> }>;
}

export interface BotMessage {
  text: string;
  isMention?: boolean;
  author: { isMe: boolean; isBot: boolean; userId?: string };
  attachments?: BotAttachment[];
}

export interface BotAttachment {
  url?: string;
  name?: string;
  mimeType?: string;
  fetchData?: () => Promise<Buffer>;
}

export interface SlackAdapter {
  fetchMessage(threadId: string, ts: string): Promise<{ attachments?: BotAttachment[] } | null>;
  setAssistantTitle(channel: string, threadTs: string, title: string): Promise<void>;
  replaceMessage(channel: string, ts: string, text: string): Promise<void>;
}

// ── Bot ───────────────────────────────────────────────────────────────────
//
// Mental model:
//   - First mention  → subscribe + buffer message + execute
//   - Non-mention in subscribed thread → buffer message (context only)
//   - Mention in subscribed thread → buffer message + execute
//

export class SlackBot {
  constructor(
    readonly client: CentaurClient,
    private viewerUrl = "",
    private slack?: SlackAdapter,
  ) {}

  static createFromEnv(slack?: SlackAdapter): SlackBot {
    return new SlackBot(
      new CentaurClient({
        apiUrl: process.env.CENTAUR_API_URL || "http://api:8000",
        apiKey: process.env.API_SECRET_KEY || "",
        logger: log,
      }),
      process.env.THREAD_VIEWER_URL || "",
      slack,
    );
  }

  // ── Handlers ────────────────────────────────────────────────────────────

  async onNewMention(thread: BotThread, msg: BotMessage) {
    if (msg.author.isMe || msg.author.isBot) return;
    await thread.subscribe();
    const attachments = await this.resolveAttachments(thread.id, msg);
    const parts = await this.toParts(msg.text, attachments);
    await this.bufferAndExecute(thread, msg.text, parts, msg.author.userId);
  }

  async onSubscribedMessage(thread: BotThread, msg: BotMessage) {
    if (msg.author.isMe || msg.author.isBot) return;

    const attachments = msg.isMention ? await this.resolveAttachments(thread.id, msg) : (msg.attachments || []);
    const text = (msg.text || "").trim();
    if (!text && !attachments.length) return;

    const parts = await this.toParts(text || "Shared attachment in thread.", attachments);
    const threadKey = normalizeThreadKey(thread.id);

    // Always buffer
    try {
      await this.client.message({ threadKey, parts, userId: msg.author.userId });
    } catch (err) {
      log.warn("message_buffer_failed", { thread: thread.id, error: err instanceof Error ? err.message : String(err) });
      return;
    }

    // Only execute on mention
    if (msg.isMention) {
      await this.execute(thread, threadKey, text, msg.author.userId);
    }
  }

  // ── Core ────────────────────────────────────────────────────────────────

  private async bufferAndExecute(thread: BotThread, text: string, parts: InputContentBlock[], userId?: string) {
    const threadKey = normalizeThreadKey(thread.id);
    await this.client.message({ threadKey, parts, userId });
    await this.execute(thread, threadKey, text, userId);
  }

  private async execute(thread: BotThread, threadKey: string, text: string, userId?: string) {
    const tracker = new ProgressTracker();
    const t0 = Date.now();
    log.info("execute_start", { thread_key: threadKey, user_id: userId });

    try {
      // Consume the SSE stream, collect result text (no streaming to Slack)
      for await (const event of this.client.execute({ threadKey, message: text, platform: "slack", userId })) {
        // Drain the generator to update tracker state (we ignore the yielded chunks)
        for (const _ of tracker.update(event)) { /* noop */ }
      }

      const finalText = (tracker.resultText || tracker.lastAssistantText).trim();
      const dur = (Date.now() - t0) / 1000;
      const durStr = dur < 10 ? `${dur.toFixed(1)}s` : `${Math.round(dur)}s`;
      log.info("execute_complete", { thread_key: threadKey, duration_s: Math.round(dur * 10) / 10, result_length: finalText.length });

      if (finalText) {
        const harness = tracker.agentThreadId
          ? `[agent](https://ampcode.com/threads/${tracker.agentThreadId})`
          : "agent";
        let md = `_${[process.env.APP_NAME || "Centaur", harness, durStr].join(" · ")}_\n\n${finalText}`;
        if (this.viewerUrl) md += `\n\n[Thread Viewer](${this.viewerUrl}/${encodeURIComponent(threadKey)})`;
        await thread.post({ markdown: md });
      } else {
        await thread.post({ markdown: "Agent completed with no output." });
      }

      if (this.slack) {
        try {
          const { channel, threadTs } = splitThreadKey(thread.id);
          await this.slack.setAssistantTitle(channel, threadTs, finalText.slice(0, 60));
        } catch (err) {
          log.warn("set_title_failed", { thread_key: threadKey, error: err instanceof Error ? err.message : String(err) });
        }
      }
    } catch (err) {
      log.error("execute_error", { thread_key: threadKey, error: err instanceof Error ? err.message : String(err) });
      try {
        await thread.post({ markdown: `Agent request failed: ${err instanceof Error ? err.message : "unknown error"}` });
      } catch (postErr) {
        log.error("error_post_failed", { thread_key: threadKey, error: postErr instanceof Error ? postErr.message : String(postErr) });
      }
    }
  }

  // ── Helpers ─────────────────────────────────────────────────────────────

  async resolveAttachments(threadId: string, msg: BotMessage): Promise<BotAttachment[]> {
    if (msg.attachments?.length) return [...msg.attachments];
    const ts = (msg as { ts?: string }).ts || "";
    if (!ts || !this.slack) return [];
    try {
      const refetched = await this.slack.fetchMessage(threadId, ts);
      if (refetched?.attachments?.length) {
        log.info("mention_files_refetched", { thread: threadId, count: refetched.attachments.length });
        return [...refetched.attachments];
      }
    } catch (err) {
      log.warn("mention_files_refetch_failed", { thread: threadId, error: err instanceof Error ? err.message : String(err) });
    }
    return [];
  }

  async toParts(text: string, attachments: BotAttachment[]): Promise<InputContentBlock[]> {
    const parts: InputContentBlock[] = [{ type: "text", text }];
    for (const att of attachments) {
      if (!att.fetchData || !att.mimeType) continue;
      try {
        const data = await att.fetchData();
        const b64 = data.toString("base64");
        const source = { type: "base64" as const, media_type: att.mimeType, data: b64 };
        parts.push(att.mimeType.startsWith("image/") ? { type: "image", source } : { type: "document", source });
      } catch (err) {
        log.warn("attachment_fetch_failed", { name: att.name || "unknown", error: err instanceof Error ? err.message : String(err) });
      }
    }
    return parts;
  }
}
