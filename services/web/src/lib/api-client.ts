import {
  resilientFetch as _resilientFetch,
  isNetworkError,
  ApiError,
  type FetchOptions,
} from "@centaur/api-client";

const API_URL = process.env.AI_V2_API_URL || "http://api:8000";
const API_KEY = process.env.AI_V2_API_KEY || "";

/**
 * Service-bound resilientFetch — injects API key and console logger.
 */
export async function resilientFetch(
  url: string,
  opts: FetchOptions = {},
): Promise<Response> {
  return _resilientFetch(url, opts, API_KEY);
}

/** POST JSON to the API with retry. Returns parsed JSON. */
export async function apiPost(
  path: string,
  payload: Record<string, unknown>,
  opts?: { timeoutMs?: number; maxAttempts?: number; signal?: AbortSignal },
): Promise<Record<string, unknown>> {
  const t0 = performance.now();
  const url = `${API_URL}${path}`;

  const res = await resilientFetch(url, {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: opts?.timeoutMs,
    maxAttempts: opts?.maxAttempts,
    signal: opts?.signal,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(
      `${path} failed (${res.status}): ${text.slice(0, 300)}`,
      res.status,
      res.status >= 500,
    );
  }

  const data = await res.json();
  const elapsed = Math.round(performance.now() - t0);
  console.log(JSON.stringify({
    event: "api_call",
    path,
    thread: payload.slack_thread_key ?? payload.thread_key ?? null,
    elapsed_ms: elapsed,
  }));

  return data;
}

/** GET from the API with retry. Returns the Response for streaming. */
export async function apiGet(
  path: string,
  params?: Record<string, string>,
  opts?: { signal?: AbortSignal; stream?: boolean; timeoutMs?: number; maxAttempts?: number },
): Promise<Response> {
  const qs = params ? `?${new URLSearchParams(params).toString()}` : "";
  const url = `${API_URL}${path}${qs}`;

  return resilientFetch(url, {
    method: "GET",
    stream: opts?.stream,
    signal: opts?.signal,
    timeoutMs: opts?.timeoutMs,
    maxAttempts: opts?.maxAttempts,
  });
}

/** Quick health probe. Returns true if API is reachable. */
export async function isApiHealthy(): Promise<boolean> {
  try {
    const res = await resilientFetch(`${API_URL}/health`, {
      timeoutMs: 3_000,
      maxAttempts: 1,
    });
    return res.ok;
  } catch {
    return false;
  }
}

export { API_URL, API_KEY, isNetworkError, ApiError };
