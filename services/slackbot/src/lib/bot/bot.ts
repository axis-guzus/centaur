import { normalizeThreadKey, splitThreadKey } from "@centaur/harness-events";
import { CentaurClient } from "@centaur/api-client";
import type { InputContentBlock } from "@centaur/api-client";

import type { StreamChunk } from "chat";
import { log } from "@/lib/logger";
import { ProgressTracker } from "./progress-tracker";

// ── Types ─────────────────────────────────────────────────────────────────

export interface BotThread {
  id: string;
  subscribe(): Promise<void>;
  post(content: AsyncGenerator<StreamChunk> | { markdown: string }): Promise<{ id: string; edit(content: { markdown: string }): Promise<void> }>;
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
      const sent = await thread.post(this.stream(threadKey, text, tracker, userId));
      const finalText = (tracker.resultText || tracker.lastAssistantText).trim();
      log.info("execute_complete", { thread_key: threadKey, duration_s: Math.round((Date.now() - t0) / 100) / 10, result_length: finalText.length });

      if (finalText) {
        await this.replaceWithFinal(thread, sent, threadKey, finalText, tracker, t0);
      }
    } catch (err) {
      if (err instanceof Error && err.message.includes("message_not_in_streaming_state")) {
        log.warn("slack_stream_expired", { thread_key: threadKey });
        await this.postRecovery(thread, threadKey);
        return;
      }
      log.error("execute_error", { thread_key: threadKey, error: err instanceof Error ? err.message : String(err) });
      await thread.post(async function* () {
        yield { type: "task_update" as const, id: "init", title: "Failed", status: "error" as const };
        yield { type: "markdown_text" as const, text: `Agent request failed: ${err instanceof Error ? err.message : "unknown error"}` };
      }());
    }
  }

  private async *stream(threadKey: string, text: string, tracker: ProgressTracker, userId?: string): AsyncGenerator<StreamChunk> {
    if (this.viewerUrl) yield { type: "markdown_text", text: `[Thread Viewer](${this.viewerUrl}/${encodeURIComponent(threadKey)})` };
    yield { type: "task_update", id: "init", title: "Starting…", status: "in_progress" };

    for await (const event of this.client.execute({ threadKey, message: text, platform: "slack", userId })) {
      yield* tracker.update(event);
    }

    if (!tracker.initCompleted) yield { type: "task_update", id: "init", title: "Started", status: "complete" };
  }

  // ── Helpers ─────────────────────────────────────────────────────────────

  private async replaceWithFinal(
    thread: BotThread,
    sent: { id: string; edit(content: { markdown: string }): Promise<void> },
    threadKey: string, text: string, tracker: ProgressTracker, t0: number,
  ) {
    const dur = (Date.now() - t0) / 1000;
    const durStr = dur < 10 ? `${dur.toFixed(1)}s` : `${Math.round(dur)}s`;
    const harness = tracker.agentThreadId
      ? `[agent](https://ampcode.com/threads/${tracker.agentThreadId})`
      : "agent";
    let md = `_${[process.env.APP_NAME || "Centaur", harness, durStr].join(" · ")}_\n\n${text}`;
    if (this.viewerUrl) md += `\n\n[Thread Viewer](${this.viewerUrl}/${encodeURIComponent(threadKey)})`;

    try {
      if (this.slack) {
        const { channel } = splitThreadKey(thread.id);
        await this.slack.replaceMessage(channel, sent.id, md);
      } else {
        await sent.edit({ markdown: md });
      }
    } catch {}

    if (this.slack) {
      try {
        const { channel, threadTs } = splitThreadKey(thread.id);
        await this.slack.setAssistantTitle(channel, threadTs, text.slice(0, 60));
      } catch {}
    }
  }

  private async postRecovery(thread: BotThread, threadKey: string) {
    try {
      const status = await this.client.getStatus(threadKey);
      const result = typeof status.last_result === "string" ? status.last_result.trim() : "";
      if (result) { await thread.post({ markdown: result }); return; }
    } catch {}
    if (this.viewerUrl) {
      await thread.post({ markdown: `Agent completed. [View full output](${this.viewerUrl}/${encodeURIComponent(threadKey)})` });
    }
  }

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
