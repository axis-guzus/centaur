/** GET /api/portfolio/positions -> POST /tools/paradigmdb/db_query */

import { resilientFetch, API_URL, ApiError } from "@/lib/api-client";
import { decode } from "@toon-format/toon";

export const dynamic = "force-dynamic";
export const fetchCache = "force-no-store";

/** Parse a tool result string that may be JSON or TOON-encoded. */
function parseResult(raw: unknown): unknown {
  if (typeof raw !== "string") return raw;
  try {
    return JSON.parse(raw);
  } catch {
    // Fall back to TOON
  }
  try {
    const decoded = decode(raw, { strict: false });
    if (decoded !== undefined) return decoded;
  } catch {
    // ignore
  }
  return raw;
}

function buildQuery(fund: string | undefined, limit: number): string {
  let sql = `SELECT p."marketValue", p."grossInvestedCapital", p."moic", p."holding", p."liquidity", p."grossRealizedValue", p."netRealizedValue", p."liquidMarketValue", p."realizedGainLoss", a.name as "assetName", a.ticker, f.name as "fundName" FROM "PerformanceLatest" p LEFT JOIN "Asset" a ON p."assetId" = a.id LEFT JOIN "Fund" f ON p."fundId" = f.id WHERE p."marketValue" > 0`;
  if (fund) {
    sql += ` AND f.name ILIKE '%${fund.replace(/'/g, "''")}%'`;
  }
  sql += ` ORDER BY p."marketValue" DESC NULLS LAST LIMIT ${limit}`;
  return sql;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const fund = searchParams.get("fund") || undefined;
  const limit = parseInt(searchParams.get("limit") || "200", 10);

  try {
    const query = buildQuery(fund, limit);

    const res = await resilientFetch(`${API_URL}/tools/paradigmdb/db_query`, {
      method: "POST",
      body: JSON.stringify({ query }),
      signal: request.signal,
      timeoutMs: 15_000,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new ApiError(`Positions API error (${res.status}): ${text.slice(0, 300)}`, res.status, res.status >= 500);
    }

    const data = await res.json();
    if (typeof data.result === "string") {
      data.result = parseResult(data.result);
    }
    return Response.json(data, { headers: { "Cache-Control": "no-store" } });
  } catch (err) {
    const status = err instanceof ApiError ? (err.status ?? 502) : 502;
    return Response.json(
      { error: err instanceof Error ? err.message : "API unreachable" },
      { status, headers: { "Cache-Control": "no-store" } },
    );
  }
}
