import { describe, expect, it, vi } from "vitest";
import { createChartRenderer } from "../src/lib/bot/chart-renderer";

describe("createChartRenderer", () => {
  it("calls the single chart.render_chart endpoint and returns PNG bytes", async () => {
    const post = vi.fn().mockResolvedValue({
      data: {
        result: Buffer.from("png-bytes").toString("base64"),
      },
    });
    const renderer = createChartRenderer({ http: { post } } as any);

    const out = await renderer({
      type: "line-chart",
      title: "BTC 30d",
      data: [{ date: "2026-04-01", price: 100 }],
    });

    expect(post).toHaveBeenCalledWith(
      "/tools/chart/render_chart",
      {
        chart_type: "line-chart",
        title: "BTC 30d",
        data: [{ date: "2026-04-01", price: 100 }],
      },
      { timeout: 8_000 },
    );
    expect(out?.toString()).toBe("png-bytes");
  });

  it("returns null when the chart tool returns an empty result", async () => {
    const post = vi.fn().mockResolvedValue({ data: { result: "" } });
    const renderer = createChartRenderer({ http: { post } } as any);

    const out = await renderer({
      type: "bar-chart",
      title: "Empty chart",
      data: [],
    });

    expect(out).toBeNull();
  });
});
