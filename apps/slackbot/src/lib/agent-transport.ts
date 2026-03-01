import type { ChatRequestOptions, ChatTransport, UIMessage, UIMessageChunk } from "ai";
import { BASE } from "@/lib/constants";

type ReplyAttachment = { url: string; name: string };

function extractMessageText(message: UIMessage): string {
  if (typeof (message as { text?: unknown }).text === "string") {
    return ((message as { text?: string }).text ?? "").trim();
  }
  const parts = (message as { parts?: Array<{ type?: string; text?: string }> }).parts ?? [];
  const textParts = parts
    .filter((part) => part.type === "text" && typeof part.text === "string")
    .map((part) => part.text ?? "");
  return textParts.join("\n").trim();
}

function normalizeAttachments(value: unknown): ReplyAttachment[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      const raw = item as { url?: unknown; name?: unknown };
      const url = typeof raw.url === "string" ? raw.url.trim() : "";
      const name = typeof raw.name === "string" ? raw.name.trim() : "";
      return { url, name };
    })
    .filter((item) => item.url && item.name);
}

async function openUiStream(
  threadKey: string,
  abortSignal: AbortSignal | undefined,
): Promise<ReadableStream<UIMessageChunk>> {
  const response = await fetch(`${BASE}/api/threads/stream-ui?key=${encodeURIComponent(threadKey)}`, {
    headers: { Accept: "text/event-stream" },
    signal: abortSignal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`stream-ui failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  return new ReadableStream<UIMessageChunk>({
    async pull(controller) {
      while (true) {
        const boundary = buffer.indexOf("\n\n");
        if (boundary >= 0) {
          const rawEvent = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const dataLines = rawEvent
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim());
          if (dataLines.length === 0) {
            continue;
          }
          const payload = dataLines.join("\n");
          if (payload === "[DONE]") {
            controller.close();
            return;
          }
          try {
            controller.enqueue(JSON.parse(payload) as UIMessageChunk);
          } catch {
            // Ignore malformed chunks to keep the stream alive.
          }
          return;
        }
        const { done, value } = await reader.read();
        if (done) {
          controller.close();
          return;
        }
        buffer += decoder.decode(value, { stream: true });
      }
    },
    cancel() {
      void reader.cancel();
    },
  });
}

export class AgentThreadTransport<UI_MESSAGE extends UIMessage = UIMessage>
  implements ChatTransport<UI_MESSAGE>
{
  constructor(private readonly threadKey: string) {}

  async sendMessages(options: {
    trigger: "submit-message" | "regenerate-message";
    chatId: string;
    messageId: string | undefined;
    messages: UI_MESSAGE[];
    abortSignal: AbortSignal | undefined;
  } & ChatRequestOptions): Promise<ReadableStream<UIMessageChunk>> {
    const lastMessage = options.messages[options.messages.length - 1];
    const text = lastMessage ? extractMessageText(lastMessage) : "";
    const body = (options.body ?? {}) as Record<string, unknown>;
    const route = String(body.route ?? "execute");
    const attachments = normalizeAttachments(body.attachments);

    if (text) {
      if (route === "reply") {
        const replyRes = await fetch(`${BASE}/api/slack/reply`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: options.abortSignal,
          body: JSON.stringify({
            thread_key: this.threadKey,
            reply: text,
            ...(attachments.length > 0 ? { attachments } : {}),
            source: "thread_ui",
            ...(options.messageId ? { message_id: options.messageId } : {}),
          }),
        });
        if (!replyRes.ok) {
          throw new Error(`reply failed (${replyRes.status})`);
        }
        const replyData = (await replyRes.json().catch(() => ({}))) as { status?: string; error?: string };
        if (replyData.error) {
          throw new Error(String(replyData.error));
        }
        if (replyData.status === "ignored_empty") {
          throw new Error("Reply is empty.");
        }
        if (replyData.status === "no_active_session") {
          throw new Error("No active engineer session for this thread.");
        }
        if (replyData.status === "not_waiting_for_reply") {
          throw new Error("Engineer is not currently waiting for a reply.");
        }
      } else {
        const executeRes = await fetch(`${BASE}/api/agent/execute`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: options.abortSignal,
          body: JSON.stringify({
            slack_thread_key: this.threadKey,
            message: text,
          }),
        });
        if (!executeRes.ok) {
          throw new Error(`execute failed (${executeRes.status})`);
        }
        const executeData = (await executeRes.json().catch(() => ({}))) as { error?: string };
        if (executeData.error) {
          throw new Error(String(executeData.error));
        }
      }
    }

    return openUiStream(this.threadKey, options.abortSignal);
  }

  async reconnectToStream(_options: {
    chatId: string;
  } & ChatRequestOptions): Promise<ReadableStream<UIMessageChunk> | null> {
    return openUiStream(this.threadKey, undefined);
  }
}
