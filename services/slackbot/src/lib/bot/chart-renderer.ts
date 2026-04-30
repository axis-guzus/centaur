/** Render dashboard chart components by calling the API chart tool. */

import type { CentaurClient } from "@centaur/api-client";
import type { ChartRenderer } from "./dashboard-to-slack";
import { log } from "@/lib/logger";

const CHART_RENDER_TIMEOUT_MS = 8_000;

interface ToolCallResponse {
  tool: string;
  method: string;
  result: string | null;
}

export function createChartRenderer(client: CentaurClient): ChartRenderer {
  return async (chart) => {
    try {
      const res = await client.http.post<ToolCallResponse>(
        "/tools/chart/render_chart",
        {
          chart_type: chart.type,
          title: chart.title,
          data: chart.data,
        },
        { timeout: CHART_RENDER_TIMEOUT_MS },
      );
      const b64 = typeof res.data?.result === "string" ? res.data.result.trim() : "";
      if (!b64) {
        log.info("dashboard_chart_empty_result", {
          chart_type: chart.type,
          chart_title: chart.title,
        });
        return null;
      }
      return Buffer.from(b64, "base64");
    } catch (err) {
      log.warn("dashboard_chart_render_failed", {
        chart_type: chart.type,
        chart_title: chart.title,
        error: err instanceof Error ? err.message : String(err),
      });
      return null;
    }
  };
}
