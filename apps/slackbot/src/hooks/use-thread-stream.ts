import { useCallback, useEffect, useMemo, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { z } from "zod";
import type { ThreadDetail } from "@/lib/types";
import { BASE } from "@/lib/constants";
import { AgentThreadTransport } from "@/lib/agent-transport";
import { stepsFromUiMessages } from "@/lib/chat-steps";

type TokenUsage = {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number | null;
  estimated: boolean;
  authoritative: boolean;
  model: string | null;
};

export function useThreadStream(threadKey: string) {
  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [agentStatus, setAgentStatus] = useState<string | null>(null);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage | null>(null);
  const transport = useMemo(() => new AgentThreadTransport(threadKey), [threadKey]);
  const chat = useChat({
    id: `thread-${threadKey}`,
    transport,
    resume: true,
    experimental_throttle: 50,
    dataPartSchemas: {
      "agent-status": z.object({ text: z.string() }),
      "phase-progress": z.object({ phase: z.string(), turn_id: z.number() }),
      "file-changes": z.object({ changes: z.array(z.object({ path: z.string(), kind: z.string() })) }),
      "user-message": z.object({
        id: z.string(),
        turn_id: z.number(),
        text: z.string(),
        source: z.string().optional(),
        user_id: z.string().nullable().optional(),
        created_at: z.string().optional(),
      }),
      "context-message": z.object({
        id: z.string(),
        turn_id: z.number(),
        text: z.string(),
        source: z.string().optional(),
        user_id: z.string().nullable().optional(),
        created_at: z.string().optional(),
      }),
      "token-usage": z.object({
        input_tokens: z.number(),
        output_tokens: z.number(),
        total_tokens: z.number(),
        cost_usd: z.number().nullable().optional(),
        estimated: z.boolean().optional(),
        authoritative: z.boolean().optional(),
        model: z.string().nullable().optional(),
      }),
    },
    onData: (part) => {
      if (part.type === "data-agent-status") {
        const data = part.data as { text?: string };
        const text = String(data.text ?? "").trim();
        setAgentStatus(text || null);
      } else if (part.type === "data-token-usage") {
        const payload = part.data as {
          input_tokens?: number;
          output_tokens?: number;
          total_tokens?: number;
          cost_usd?: number | null;
          estimated?: boolean;
          authoritative?: boolean;
          model?: string | null;
        };
        setTokenUsage({
          input_tokens: Number(payload.input_tokens ?? 0),
          output_tokens: Number(payload.output_tokens ?? 0),
          total_tokens: Number(payload.total_tokens ?? 0),
          cost_usd:
            payload.cost_usd === null || payload.cost_usd === undefined
              ? null
              : Number(payload.cost_usd),
          estimated: Boolean(payload.estimated),
          authoritative: Boolean(payload.authoritative),
          model: payload.model ? String(payload.model) : null,
        });
      }
    },
    onFinish: () => {
      setAgentStatus(null);
    },
  });

  const fetchThread = useCallback(async () => {
    try {
      const res = await fetch(
        `${BASE}/api/threads/detail?key=${encodeURIComponent(threadKey)}`
      );
      if (!res.ok) {
        setThread(null);
        setError(`Thread not found: ${threadKey}`);
        return;
      }
      const data = await res.json();
      if (data.error) {
        setThread(null);
        setError(String(data.error));
        return;
      }
      setThread(data as ThreadDetail);
      setError(null);
    } catch {
      setThread(null);
      setError("Failed to fetch thread");
    }
  }, [threadKey]);

  useEffect(() => {
    setThread(null);
    setError(null);
    setIsPolling(false);
    setAgentStatus(null);
    setTokenUsage(null);
    void fetchThread();
    const poll = setInterval(() => {
      setIsPolling(true);
      void fetchThread().finally(() => setIsPolling(false));
    }, 5000);

    return () => {
      clearInterval(poll);
    };
  }, [threadKey, fetchThread]);

  const sendReply = useCallback(
    async (message: string) => {
      const text = message.trim();
      if (!text) return;
      await chat.sendMessage({ text }, { body: { route: "reply" } });
    },
    [chat],
  );
  const liveSteps = useMemo(() => stepsFromUiMessages(chat.messages), [chat.messages]);

  return {
    thread,
    error,
    fetchThread,
    isReconnecting: isPolling || chat.status === "error",
    agentStatus,
    tokenUsage,
    chatStatus: chat.status,
    sendReply,
    liveSteps,
  };
}
