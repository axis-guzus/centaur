/**
 * GET /api/messages?key={thread_key}&limit=N&before={id}
 *
 * Proxies to the Python API's GET /agent/messages endpoint.
 */

import { NextRequest } from "next/server";
import { safeValidateUIMessages } from "ai";
import { dataPartSchemas } from "@/lib/data-part-schemas";
import { resilientFetch, API_URL } from "@/lib/api-client";

export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";

export async function GET(request: NextRequest) {
  const threadKey = request.nextUrl.searchParams.get("key");
  if (!threadKey) {
    return Response.json({ error: "Missing key parameter" }, { status: 400 });
  }

  const limitParam = request.nextUrl.searchParams.get("limit");
  const beforeId = request.nextUrl.searchParams.get("before");
  const limit = limitParam ? Math.max(1, Math.min(200, parseInt(limitParam, 10) || 200)) : null;

  try {
    // Build query params for the API
    const params = new URLSearchParams({ thread_key: threadKey });
    if (limit !== null) params.set("limit", String(limit));
    if (beforeId) params.set("cursor", beforeId);

    const res = await resilientFetch(
      `${API_URL}/agent/messages?${params.toString()}`,
      { timeoutMs: 10_000 },
    );

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return Response.json(
        { error: `API error: ${res.status}`, detail: text.slice(0, 500) },
        { status: res.status, headers: { "Cache-Control": "no-store" } },
      );
    }

    const data = await res.json();

    // API returns { messages, cursor, has_more }
    // Map to the format the web UI expects
    const messages = (data.messages || []).map((row: Record<string, unknown>) => ({
      id: row.id as string,
      role: row.role as string,
      parts: row.parts,
      createdAt: row.created_at ? new Date(row.created_at as string).toISOString() : null,
      metadata: row.metadata,
    }));

    const validated = await safeValidateUIMessages({
      messages,
      dataSchemas: dataPartSchemas,
    });

    const validatedMessages = validated.success ? validated.data : messages;

    if (limit !== null) {
      return Response.json(
        { messages: validatedMessages, has_more: data.has_more || false },
        { headers: { "Cache-Control": "no-store" } },
      );
    }

    // Backwards-compatible: flat array
    return Response.json(validatedMessages, {
      headers: { "Cache-Control": "public, s-maxage=5, stale-while-revalidate=3" },
    });
  } catch (err) {
    console.error("Failed to fetch messages:", err);
    return Response.json(
      { error: err instanceof Error ? err.message : "API error" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
