import crypto from "node:crypto";
import { Chat, parseMarkdown, type Root } from "chat";
import { createSlackAdapter } from "@chat-adapter/slack";
import { createRedisState } from "@chat-adapter/state-redis";
import { createMemoryState } from "@chat-adapter/state-memory";
import {
  execute,
  extractRunOptions,
  normalizeThreadKey,
  replyEngineerFlow,
  spawn,
  startEngineerFlow,
  type AgentMode,
  type BudgetMode,
  type FileAttachment,
} from "./harness";
import { truncateSlackText } from "./slack-text";

const THREAD_VIEWER_URL = process.env.THREAD_VIEWER_URL || "https://svc-ai.paradigm.xyz";
const MAX_TRACKED_THREAD_MODES = 500;

type MarkdownNode = Root | Root["children"][number];
type ThreadModeConfig = {
  mode: AgentMode;
  modelPreference: string | null;
  budgetMode: BudgetMode | null;
};

function renderSlackMessage(markdown: string) {
  const ast = parseMarkdown(markdown);
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
    userName: "tempo-ai",
    adapters: hasSlackCreds ? { slack: createSlackAdapter() } : {},
    state: process.env.REDIS_URL ? createRedisState() : createMemoryState(),
  });
  const threadModes = new Map<string, ThreadModeConfig>();

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
      "- Preserve Slack user mentions (`<@UXXXXXXX>`) exactly as-is",
      "- Use `<URL|Display Text>` format for hyperlinks — never put URLs adjacent to `*` or `_`",
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
    attachments?: Array<{ url?: string; name?: string }>
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
          "Please provide a prompt after flags. Example: `@tempo-ai --eng --claude implement retry logic`"
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

    setThreadMode(threadKey, { mode: "default", modelPreference: null, budgetMode: null });
    const harness = parsed.harness ?? "amp";
    try {
      await thread.startTyping("Spawning agent...");
      await spawn(threadKey, harness, undefined, requestId);

      await thread.startTyping("Running...");
      const message = isFirstMessage
        ? buildSessionContext(threadKey) + parsed.cleanedText
        : parsed.cleanedText;
      const result = await execute(
        threadKey,
        message,
        harness,
        requestId,
        files.length > 0 ? files : undefined
      );

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
    await handleMessage(thread, message.text, true, attachments);
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
    await handleMessage(thread, message.text, false, attachments);
  });

  return bot;
}

let _bot: ReturnType<typeof createBot> | null = null;
export function getBot() {
  if (!_bot) _bot = createBot();
  return _bot;
}
