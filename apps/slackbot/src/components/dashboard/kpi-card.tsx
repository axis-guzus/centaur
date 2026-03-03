"use client";

import type { KPICardProps } from "./types";
import { formatValue } from "./format-value";

export function KPICard({ label, value, format, delta }: Omit<KPICardProps, "type">) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-foreground">
        {formatValue(value, format)}
      </p>
      {delta != null && (
        <p
          className={`mt-1 text-sm font-medium ${
            delta >= 0 ? "text-emerald-500" : "text-red-500"
          }`}
        >
          {delta >= 0 ? "↑" : "↓"}
          {Math.abs(delta).toFixed(1)}%
        </p>
      )}
    </div>
  );
}
