/**
 * POST /api/agent/execute
 *
 * Accepts { slack_thread_key, message, harness? } from the client.
 * Calls the Python pipe server, reads raw harness SSE events, converts them
 * to AI SDK v6 UIMessageChunk objects server-side, and returns a proper
 * AI SDK UIMessage stream response.
 *
 * The client can consume this with DefaultChatTransport / HttpChatTransport
 * — no custom SSE parsing needed on the client side.
 */

import { z } from "zod";
import {
  createUIMessageStreamResponse,
  createUIMessageStream,
  createIdGenerator,
  parseJsonEventStream,
} from "ai";
import type { UIMessage } from "ai";
import { resilientFetch, API_URL, ApiError } from "@/lib/api-client";
import {
  canonicalEventToStreamChunks,
  createConversionState,
} from "@/lib/harness-to-ui-chunks";
import { normalizeHarnessEvent } from "@centaur/harness-events";

const generateMessageId = createIdGenerator({ prefix: "msg", size: 16 });

export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";
export const maxDuration = 300;

const rawEventSchema = z.record(z.string(), z.unknown());

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const slackThreadKey = String(body.slack_thread_key ?? "").trim();
  const message = String(body.message ?? "").trim();
  const harness =
    typeof body.harness === "string" && body.harness.trim().length > 0
      ? body.harness.trim()
      : "amp";
  const engine =
    typeof body.engine === "string" && body.engine.trim().length > 0
      ? body.engine.trim()
      : "";
  const originalMessages: UIMessage[] = Array.isArray(body.messages) ? body.messages : [];

  if (!slackThreadKey || !message) {
    return Response.json(
      { error: "Missing slack_thread_key or message" },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }

  // Buffer the user message via POST /agent/messages
  try {
    await resilientFetch(`${API_URL}/agent/messages`, {
      method: "POST",
      body: JSON.stringify({
        thread_key: slackThreadKey,
        role: "user",
        parts: [{ type: "text", text: message }],
        metadata: { source: "thread_ui" },
      }),
      timeoutMs: 10_000,
    });
  } catch (err) {
    console.warn("Failed to buffer user message:", err);
  }

  let upstream: Response;
  try {
    upstream = await resilientFetch(`${API_URL}/agent/execute`, {
      method: "POST",
      body: JSON.stringify({
        thread_key: slackThreadKey,
        message,
        harness,
        ...(engine ? { engine } : {}),
      }),
      stream: true,
    });
  } catch (err) {
    const status = err instanceof ApiError ? (err.status ?? 502) : 502;
    return Response.json(
      { error: err instanceof Error ? err.message : "API unreachable" },
      { status, headers: { "Cache-Control": "no-store" } },
    );
  }

  if (!upstream.ok) {
    const text = await upstream.text().catch(() => "");
    return Response.json(
      { error: `Execute failed: ${upstream.status}`, detail: text.slice(0, 500) },
      { status: upstream.status, headers: { "Cache-Control": "no-store" } },
    );
  }

  if (!upstream.body) {
    return Response.json(
      { error: "No response body from pipe server" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  const rawEvents = parseJsonEventStream({
    stream: upstream.body,
    schema: rawEventSchema,
  });

  let eventIndex = 0;
  const conversionState = createConversionState();

  const uiChunkStream = rawEvents.pipeThrough(
    new TransformStream({
      transform(parseResult, controller) {
        if (!parseResult.success) return;
        const rawEvent = parseResult.value;
        const canonicalEvents = normalizeHarnessEvent(harness, rawEvent);
        const chunks = canonicalEvents.flatMap((event, offset) =>
          canonicalEventToStreamChunks(0, eventIndex + offset, event, conversionState),
        );
        eventIndex += Math.max(1, canonicalEvents.length);
        for (const chunk of chunks) {
          controller.enqueue(chunk);
        }
      },
    }),
  );

  return createUIMessageStreamResponse({
    stream: createUIMessageStream({
      originalMessages,
      generateId: generateMessageId,
      execute: async ({ writer }) => {
        writer.merge(uiChunkStream);
      },
    }),
  });
}
