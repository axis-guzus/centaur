import crypto from "node:crypto";
import { Chat, parseMarkdown, type Root } from "chat";
import { createSlackAdapter } from "@chat-adapter/slack";
import { createRedisState } from "@chat-adapter/state-redis";
import { createMemoryState } from "@chat-adapter/state-memory";
import {
  execute,
  extractRunOptions,
  interrupt,
  normalizeThreadKey,
  replyEngineerFlow,
  spawn,
  startEngineerFlow,
  type AgentMode,
  type BudgetMode,
  type FileAttachment,
  type Harness,
} from "./harness";
import { truncateSlackText } from "./slack-text";

const THREAD_VIEWER_URL = process.env.THREAD_VIEWER_URL || "https://svc-ai.paradigm.xyz";
const MAX_TRACKED_THREAD_MODES = 500;
const SLACK_API_BASE = "https://slack.com/api";
const MAX_SLACK_CONTEXT_MESSAGES = 18;
const MAX_SLACK_CONTEXT_CHARS = 6000;
const SLACK_BOT_USERNAME = process.env.SLACK_BOT_USERNAME || "paradigm-ai";
const SLACK_RETRY_ATTEMPTS = 3;
const DEFAULT_SLACK_RETRY_MS = 1000;

type MarkdownNode = Root | Root["children"][number];
type ThreadModeConfig = {
  mode: AgentMode;
  modelPreference: string | null;
  budgetMode: BudgetMode | null;
};
type SlackReplyMessage = {
  ts?: string;
  text?: string;
  user?: string;
  bot_id?: string;
  subtype?: string;
};
type SlackDiscussionContext = {
  instruction: string;
  latestTs: string | null;
};

const HARNESSES: readonly Harness[] = ["amp", "claude-code", "codex", "pi-mono"] as const;
let cachedBotUserId: string | null | undefined;

function isHarness(value: string | null | undefined): value is Harness {
  return HARNESSES.includes((value ?? "") as Harness);
}

function splitThreadKey(threadKey: string): { channel: string; threadTs: string } {
  const parts = threadKey.trim().split(":");
  if (parts.length === 2 && parts[0] && parts[1]) {
    return { channel: parts[0], threadTs: parts[1] };
  }
  if (parts.length === 3 && parts[0].toLowerCase() === "slack" && parts[1] && parts[2]) {
    return { channel: parts[1], threadTs: parts[2] };
  }
  throw new Error(`Invalid thread key format: ${threadKey}`);
}

function tsToNumber(ts: string): number {
  const parsed = Number.parseFloat(ts);
  return Number.isFinite(parsed) ? parsed : 0;
}

function compactText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function retryAfterMs(response: Response): number {
  const retryAfter = response.headers.get("Retry-After");
  const parsed = Number(retryAfter);
  if (!Number.isFinite(parsed) || parsed <= 0) return DEFAULT_SLACK_RETRY_MS;
  return Math.max(DEFAULT_SLACK_RETRY_MS, Math.min(parsed * 1000, 30_000));
}

async function slackGet<T extends Record<string, unknown>>(
  token: string,
  path: string,
  query: Record<string, string>,
): Promise<T> {
  const url = new URL(`${SLACK_API_BASE}/${path}`);
  for (const [k, v] of Object.entries(query)) {
    if (v) url.searchParams.set(k, v);
  }
  for (let attempt = 0; attempt < SLACK_RETRY_ATTEMPTS; attempt += 1) {
    const response = await fetch(url.toString(), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.status === 429 && attempt + 1 < SLACK_RETRY_ATTEMPTS) {
      await sleep(retryAfterMs(response));
      continue;
    }
    if (!response.ok) {
      throw new Error(`Slack API ${path} failed (${response.status})`);
    }
    const data = (await response.json()) as T & { ok?: boolean; error?: string };
    if (data.ok === true) {
      return data;
    }
    if (data.error === "ratelimited" && attempt + 1 < SLACK_RETRY_ATTEMPTS) {
      await sleep(retryAfterMs(response));
      continue;
    }
    throw new Error(`Slack API ${path} error: ${data.error || "unknown_error"}`);
  }
  throw new Error(`Slack API ${path} failed after ${SLACK_RETRY_ATTEMPTS} attempts`);
}

async function getBotUserId(token: string): Promise<string | null> {
  if (cachedBotUserId !== undefined) return cachedBotUserId;
  try {
    const data = await slackGet<{ user_id?: string }>(token, "auth.test", {});
    cachedBotUserId = typeof data.user_id === "string" && data.user_id ? data.user_id : null;
  } catch {
    cachedBotUserId = null;
  }
  return cachedBotUserId;
}

function isBusyRunError(message: string): boolean {
  const normalized = message.toLowerCase();
  return normalized.includes("already in progress") || normalized.includes("run is already in progress");
}

/**
 * Convert Slack-style links to markdown before AST parsing.
 * LLMs sometimes output `<url|text>` or `&lt;url|text&gt;` despite being
 * told to use markdown — this catches those and converts them so
 * the markdown parser produces proper link nodes.
 */
function preprocessSlackLinks(text: string): string {
  let result = text;
  // HTML-encoded Slack links: &lt;https://...|text&gt; → [text](url)
  result = result.replace(/&lt;(https?:\/\/[^|&]+)\|([^&]+)&gt;/g, "[$2]($1)");
  // Raw Slack links: <https://...|text> → [text](url)
  // Only matches URLs (not Slack mentions like <@U...> or <#C...>)
  result = result.replace(/<(https?:\/\/[^|>]+)\|([^>]+)>/g, "[$2]($1)");
  return result;
}

function renderSlackMessage(markdown: string) {
  const ast = parseMarkdown(preprocessSlackLinks(markdown));
  const escapeLiteralTildes = (
    node: MarkdownNode,
    inDelete = false
  ): void => {
    const insideDelete = inDelete || node.type === "delete";

    if (node.type === "text" && !insideDelete) {
      // Slack treats paired single tildes as strikethrough; escape literal tildes.
      node.value = node.value.replace(/~/g, "\\~");
    }

    if ("children" in node && Array.isArray(node.children)) {
      for (const child of node.children as Root["children"]) {
        escapeLiteralTildes(child, insideDelete);
      }
    }
  };

  escapeLiteralTildes(ast);

  return { ast };
}

function toSlackMessage(markdown: string) {
  return renderSlackMessage(truncateSlackText(markdown));
}

function createBot() {
  const hasSlackCreds =
    process.env.SLACK_BOT_TOKEN && process.env.SLACK_SIGNING_SECRET;

  const bot = new Chat({
    userName: SLACK_BOT_USERNAME,
    adapters: hasSlackCreds ? { slack: createSlackAdapter() } : {},
    state: process.env.REDIS_URL ? createRedisState() : createMemoryState(),
  });
  const threadModes = new Map<string, ThreadModeConfig>();
  const threadContextWatermarks = new Map<string, string>();

  function setThreadMode(threadKey: string, config: ThreadModeConfig): void {
    if (threadModes.has(threadKey)) {
      threadModes.delete(threadKey);
    }
    if (!threadModes.has(threadKey) && threadModes.size >= MAX_TRACKED_THREAD_MODES) {
      const oldestKey = threadModes.keys().next().value as string | undefined;
      if (oldestKey) threadModes.delete(oldestKey);
    }
    threadModes.set(threadKey, config);
  }

  function setContextWatermark(threadKey: string, ts: string | null): void {
    if (!ts) return;
    if (threadContextWatermarks.has(threadKey)) {
      threadContextWatermarks.delete(threadKey);
    }
    if (!threadContextWatermarks.has(threadKey) && threadContextWatermarks.size >= MAX_TRACKED_THREAD_MODES) {
      const oldestKey = threadContextWatermarks.keys().next().value as string | undefined;
      if (oldestKey) threadContextWatermarks.delete(oldestKey);
    }
    threadContextWatermarks.set(threadKey, ts);
  }

  async function buildSlackDiscussionContext(
    threadKey: string,
    instruction: string,
  ): Promise<SlackDiscussionContext> {
    const token = process.env.SLACK_BOT_TOKEN || "";
    if (!token) return { instruction, latestTs: null };

    let channel = "";
    let threadTs = "";
    try {
      const parsed = splitThreadKey(threadKey);
      channel = parsed.channel;
      threadTs = parsed.threadTs;
    } catch {
      return { instruction, latestTs: null };
    }

    try {
      const data = await slackGet<{ messages?: SlackReplyMessage[] }>(token, "conversations.replies", {
        channel,
        ts: threadTs,
        limit: "200",
      });
      const messages = Array.isArray(data.messages) ? data.messages : [];
      const latestTs = messages.length > 0 ? String(messages[messages.length - 1]?.ts || "") : null;
      const watermark = threadContextWatermarks.get(threadKey);
      const botUserId = await getBotUserId(token);
      const isBotLikeMessage = (raw: SlackReplyMessage): boolean =>
        Boolean(raw?.bot_id) ||
        String(raw?.subtype || "").toLowerCase() === "bot_message" ||
        (botUserId ? String(raw?.user || "") === botUserId : false);
      const explicitMentionToBot = (text: string): boolean =>
        Boolean(botUserId) && text.includes(`<@${botUserId}>`);

      let watermarkNum = watermark ? tsToNumber(watermark) : 0;
      if (!watermark) {
        for (let idx = messages.length - 1; idx >= 0; idx -= 1) {
          const candidate = messages[idx];
          const candidateText = compactText(String(candidate?.text || ""));
          if (!candidate?.ts) continue;
          if (isBotLikeMessage(candidate) || explicitMentionToBot(candidateText)) {
            watermarkNum = tsToNumber(String(candidate.ts));
            break;
          }
        }
      }

      const contextLines: string[] = [];
      for (const raw of messages) {
        const ts = String(raw?.ts || "");
        if (!ts) continue;
        if (tsToNumber(ts) <= watermarkNum) continue;

        const text = compactText(String(raw?.text || ""));
        if (!text) continue;

        const isBotMessage = isBotLikeMessage(raw);
        if (isBotMessage) continue;

        if (explicitMentionToBot(text)) {
          // Explicit AI command message itself; keep as instruction, not ambient context.
          continue;
        }

        const author = String(raw?.user || "").trim();
        const prefix = author ? `<@${author}>` : "thread-user";
        contextLines.push(`- ${prefix}: ${text}`);
      }

      if (contextLines.length === 0) {
        return { instruction, latestTs };
      }

      const selected = contextLines.slice(-MAX_SLACK_CONTEXT_MESSAGES);
      let contextBlock =
        "Additional Slack thread context since the last AI instruction (ambient discussion from humans):\n" +
        selected.join("\n");
      if (contextBlock.length > MAX_SLACK_CONTEXT_CHARS) {
        contextBlock = contextBlock.slice(0, MAX_SLACK_CONTEXT_CHARS).trimEnd() + "\n- ... (truncated)";
      }
      return {
        instruction: `${instruction}\n\n${contextBlock}`,
        latestTs,
      };
    } catch (error) {
      console.warn("slack_context_fetch_failed", {
        thread: threadKey,
        error: error instanceof Error ? error.message : String(error),
      });
      return { instruction, latestTs: null };
    }
  }

  function buildSessionContext(threadId: string): string {
    const now = new Date().toISOString().replace("T", " ").slice(0, 19);
    return [
      "# Session Context",
      "",
      `- **Date/Time**: ${now} UTC`,
      `- **Thread ID**: ${threadId}`,
      `- **Platform**: Slack`,
      "",
      "## Slack Formatting Rules",
      "",
      "- Use standard markdown links `[Display Text](URL)` for all hyperlinks — they are auto-converted to Slack format",
      "- Do NOT use Slack-native `<URL|text>` link syntax — it breaks the rendering pipeline",
      "- Preserve Slack user mentions (`<@UXXXXXXX>`) exactly as-is — only use these for actual Slack users",
      "- For Twitter/X handles, always link to the profile: `[@handle](https://x.com/handle)` — bare @handle gets auto-converted to a broken Slack mention",
      "- Slack enforces a 4,000 character limit per message — split long responses across multiple messages or summarize",
      "- Use Slack Block Kit formatting for tables, not markdown or ASCII",
      "- After completing a long task, tag the requester with `@username`",
      "",
      "---",
      "",
    ].join("\n");
  }

  async function handleMessage(
    thread: Parameters<Parameters<typeof bot.onNewMention>[0]>[0],
    messageText: string,
    isFirstMessage: boolean,
    attachments?: Array<{ url?: string; name?: string }>,
    userId?: string,
  ) {
    const parsed = extractRunOptions(messageText);
    const requestId = crypto.randomUUID().slice(0, 8);
    const rawThreadKey = thread.id;
    const threadKey = normalizeThreadKey(rawThreadKey);
    const previous = threadModes.get(threadKey);
    const files: FileAttachment[] = (attachments || [])
      .filter((a): a is { url: string; name: string } => !!a.url && !!a.name)
      .map((a) => ({ url: a.url, name: a.name }));

    const ampEngRequested =
      parsed.mode === "eng" &&
      (parsed.modelPreference === "amp" || parsed.harness === "amp");
    const requestedMode: AgentMode = ampEngRequested ? "default" : parsed.mode;
    const mode: AgentMode = isFirstMessage
      ? requestedMode
      : (previous?.mode ?? requestedMode);

    if (
      !isFirstMessage &&
      previous &&
      parsed.modeExplicit &&
      requestedMode !== previous.mode
    ) {
      await thread.post(
        toSlackMessage(
          "This thread is already running in a different mode. Start a new thread to switch modes."
        )
      );
      return;
    }

    if (ampEngRequested && isFirstMessage) {
      await thread.post(
        toSlackMessage(
          "Routing `--eng --amp` through standard `--amp` mode for reliability."
        )
      );
    }

    if (!parsed.cleanedText) {
      await thread.post(
        toSlackMessage(
          "Please provide a prompt after flags. Example: `--eng --claude implement retry logic` (after mentioning the bot)."
        )
      );
      return;
    }

    // Recovery path: after bot restarts we may lose in-memory mode state,
    // so probe the API for an active engineer session before default routing.
    if (
      !isFirstMessage &&
      !previous &&
      !parsed.modeExplicit &&
      !parsed.harnessExplicit &&
      !parsed.budgetExplicit
    ) {
      try {
        const reply = await replyEngineerFlow(threadKey, parsed.cleanedText);
        if (reply.status === "accepted") {
          setThreadMode(threadKey, {
            mode: "eng",
            modelPreference: null,
            budgetMode: null,
          });
          return;
        }
      } catch (error) {
        console.warn("engineer_recovery_probe_failed", {
          thread: threadKey,
          error: error instanceof Error ? error.message : String(error),
        });
        await thread.post(
          toSlackMessage(
            "Couldn't verify the existing engineer session right now. Please retry in this thread."
          )
        );
        return;
      }
    }

    if (mode === "eng") {
      const modelPreference =
        parsed.modelPreference ?? parsed.harness ?? previous?.modelPreference ?? null;
      const budgetMode = parsed.budgetMode ?? previous?.budgetMode ?? null;

      try {
        if (isFirstMessage) {
          await thread.startTyping("Starting engineer flow...");
          const result = await startEngineerFlow(
            threadKey,
            parsed.cleanedText,
            modelPreference,
            budgetMode,
            files.length > 0 ? files : undefined
          );
          const viewerUrl = `${THREAD_VIEWER_URL}/threads/${encodeURIComponent(normalizeThreadKey(threadKey))}`;
          const preferenceLine = modelPreference
            ? `\nModel preference: \`${modelPreference}\``
            : "";
          const modeLine = budgetMode ? `\nMode: \`${budgetMode}\`` : "";
          const statusLine = (() => {
            if (result.status === "already_running") {
              setThreadMode(threadKey, { mode: "eng", modelPreference, budgetMode });
              return "Engineer flow is already running for this thread.";
            }
            if (result.status === "rejected") {
              return (
                result.error ??
                "Engineer flow could not start because another harness session is active in this thread."
              );
            }
            setThreadMode(threadKey, { mode: "eng", modelPreference, budgetMode });
            return "Engineer flow started.";
          })();
          await thread.post(
            toSlackMessage(
              `[🔗 Thread Viewer](${viewerUrl})\n\n${statusLine}${preferenceLine}${modeLine}`
            )
          );
          return;
        }

        const reply = await replyEngineerFlow(
          threadKey,
          parsed.cleanedText,
          files.length > 0 ? files : undefined
        );
        if (reply.status === "no_active_session") {
          threadModes.delete(threadKey);
          await thread.post(
            toSlackMessage(
              "No active engineer session for this thread. Start a new run with `--eng`."
            )
          );
        } else if (reply.status === "not_waiting_for_reply") {
          await thread.post(
            toSlackMessage("Engineer is not currently waiting for a reply.")
          );
        } else if (reply.status === "accepted") {
          setThreadMode(threadKey, { mode: "eng", modelPreference, budgetMode });
        }
        return;
      } catch (error) {
        await thread.post(
          toSlackMessage(
            `Engineer flow request failed: ${
              error instanceof Error ? error.message : "unknown error"
            }`
          )
        );
        return;
      }
    }

    const previousHarness =
      previous?.mode === "default" && isHarness(previous.modelPreference)
        ? previous.modelPreference
        : null;
    const harness = parsed.harness ?? previousHarness ?? "amp";
    setThreadMode(threadKey, { mode: "default", modelPreference: harness, budgetMode: null });
    try {
      let instruction = parsed.cleanedText;
      let nextWatermark: string | null = null;
      if (isFirstMessage) {
        nextWatermark = (Date.now() / 1000).toFixed(6);
      } else {
        const discussion = await buildSlackDiscussionContext(threadKey, instruction);
        instruction = discussion.instruction;
        nextWatermark = discussion.latestTs;
        try {
          await interrupt(threadKey, requestId);
        } catch (error) {
          console.warn("agent_interrupt_failed", {
            thread: threadKey,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      }

      await thread.startTyping("Spawning agent...");
      await spawn(threadKey, harness, undefined, requestId);

      await thread.startTyping("Running...");
      const message = isFirstMessage
        ? buildSessionContext(threadKey) + instruction
        : instruction;

      let result = "";
      const maxAttempts = 4;
      for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        try {
          result = await execute(
            threadKey,
            message,
            harness,
            requestId,
            files.length > 0 ? files : undefined,
            userId,
            "slack",
          );
          break;
        } catch (error) {
          const detail = error instanceof Error ? error.message : String(error);
          const shouldRetry = isBusyRunError(detail) && attempt < maxAttempts;
          if (!shouldRetry) {
            throw error;
          }
          await sleep(350 * attempt);
        }
      }
      setContextWatermark(threadKey, nextWatermark);

      let finalMessage = result;
      if (isFirstMessage) {
        const viewerUrl = `${THREAD_VIEWER_URL}/threads/${encodeURIComponent(normalizeThreadKey(threadKey))}`;
        finalMessage = `[🔗 Thread Viewer](${viewerUrl})\n\n` + finalMessage;
      }
      await thread.post(toSlackMessage(finalMessage));
    } catch (error) {
      await thread.post(
        toSlackMessage(
          `Agent request failed: ${
            error instanceof Error ? error.message : "unknown error"
          }`
        )
      );
    }
  }

  bot.onNewMention(async (thread, message) => {
    if (message.author.isMe) return;
    if (message.author.isBot) return;
    await thread.subscribe();
    const attachments = message.attachments?.map((a) => ({ url: a.url, name: a.name }));
    await handleMessage(thread, message.text, true, attachments, message.author.userId);
  });

  bot.onSubscribedMessage(async (thread, message) => {
    if (message.author.isMe) return;
    if (message.author.isBot) return;
    const attachments = message.attachments?.map((a) => ({ url: a.url, name: a.name }));
    if (!message.isMention) {
      // Allow plain thread replies to resume engineer clarification when session is active
      const text = (message.text || "").trim();
      if (!text) return;
      const threadKey = normalizeThreadKey(thread.id);
      const knownMode = threadModes.get(threadKey)?.mode;
      try {
        const files: FileAttachment[] = (attachments || [])
          .filter((a): a is { url: string; name: string } => !!a.url && !!a.name)
          .map((a) => ({ url: a.url, name: a.name }));
        const reply = await replyEngineerFlow(threadKey, text, files.length > 0 ? files : undefined);
        if (reply.status === "accepted") return;
        if (reply.status === "not_waiting_for_reply") {
          if (knownMode === "eng") {
            await thread.post(
              toSlackMessage("Engineer is not currently waiting for a reply.")
            );
          }
          return;
        }
        if (reply.status === "no_active_session" && knownMode === "eng") {
          threadModes.delete(threadKey);
          await thread.post(
            toSlackMessage("No active engineer session for this thread. Start a new run with `--eng`.")
          );
          return;
        }
      } catch (error) {
        console.warn("engineer_plain_reply_failed", {
          thread: threadKey,
          error: error instanceof Error ? error.message : String(error),
        });
        if (knownMode === "eng") {
          await thread.post(
            toSlackMessage("Could not deliver your reply to engineer right now. Please retry.")
          );
        }
      }
      return;
    }
    await handleMessage(thread, message.text, false, attachments, message.author.userId);
  });

  return bot;
}

let _bot: ReturnType<typeof createBot> | null = null;
export function getBot() {
  if (!_bot) _bot = createBot();
  return _bot;
}
