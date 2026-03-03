"use client";

import {
  ResponsiveContainer,
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import type { LineChartProps } from "./types";
import { formatValue } from "./format-value";

const COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#f43f5e", "#8b5cf6"];

export function DashboardLineChart({
  title,
  xKey,
  yKeys,
  data,
  xFormat,
  yFormat,
}: Omit<LineChartProps, "type">) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="mb-3 text-sm font-medium text-foreground">{title}</h3>
      <ResponsiveContainer width="100%" height={300}>
        <RechartsLineChart data={data}>
          <XAxis
            dataKey={xKey}
            tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }}
            tickFormatter={(v) => (xFormat ? formatValue(v, xFormat) : String(v))}
            stroke="var(--color-border)"
          />
          <YAxis
            tick={{ fontSize: 11, fill: "var(--color-muted-foreground)" }}
            tickFormatter={(v) => (yFormat ? formatValue(v, yFormat) : String(v))}
            stroke="var(--color-border)"
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--color-card)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              fontSize: 12,
              color: "var(--color-foreground)",
            }}
            formatter={(v: unknown) => (yFormat ? formatValue(v, yFormat) : String(v))}
            labelFormatter={(l: unknown) => (xFormat ? formatValue(l, xFormat) : String(l))}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, color: "var(--color-muted-foreground)" }}
          />
          {yKeys.map((key, i) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </RechartsLineChart>
      </ResponsiveContainer>
    </div>
  );
}
