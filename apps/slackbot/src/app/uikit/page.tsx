"use client";

import { useState, useMemo } from "react";
import { Textarea } from "@/components/ui/textarea";
import { DashboardLayout } from "@/components/dashboard/layout";
import { parseDashboardSpec } from "@/lib/dashboard-parser";
import type { DashboardSpec } from "@/components/dashboard/types";

const SAMPLE_DASHBOARD = `title: Portfolio Summary
layout: grid-3
---
type: kpi-card
label: Total NAV
value: 1250000000
format: currency
---
type: kpi-card
label: MTD Return
value: 3.2
format: percent
delta: 1.5
---
type: kpi-card
label: Positions
value: 42
format: number
delta: -2.3
---
type: data-table
title: Top Holdings
columns: name:text,value:currency,weight:percent,mtdReturn:percent
searchable: true
defaultSort: value,desc
data:
  [7]{name,value,weight,mtdReturn}:
    ETH,450000000,36.0,5.2
    BTC,320000000,25.6,2.1
    SOL,180000000,14.4,8.7
    AVAX,95000000,7.6,-3.1
    MATIC,72000000,5.8,1.9
    DOGE,48000000,3.8,12.4
    LINK,35000000,2.8,-0.5
---
type: line-chart
title: Portfolio NAV (30d)
xKey: date
yKeys: nav,benchmark
xFormat: date
yFormat: currency
data:
  [7]{date,nav,benchmark}:
    2026-02-01,1180000000,1200000000
    2026-02-05,1195000000,1190000000
    2026-02-10,1210000000,1205000000
    2026-02-15,1225000000,1210000000
    2026-02-20,1240000000,1215000000
    2026-02-25,1235000000,1220000000
    2026-03-01,1250000000,1225000000
---
type: bar-chart
title: Sector Allocation
categoryKey: sector
valueKey: allocation
data:
  [5]{sector,allocation}:
    DeFi,42
    L1,28
    Gaming,12
    NFT,10
    Infra,8
---
type: pie-chart
title: Chain Exposure
labelKey: chain
valueKey: weight
data:
  [5]{chain,weight}:
    Ethereum,45
    Solana,25
    Avalanche,15
    Polygon,10
    Other,5`;

export default function UIKitPage() {
  const [raw, setRaw] = useState(SAMPLE_DASHBOARD);

  const spec = useMemo<DashboardSpec | null>(() => {
    return parseDashboardSpec(raw);
  }, [raw]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-8 px-6 py-8">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Dashboard UI Kit</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Live preview of all dashboard components. Edit the TOON spec below to test parsing.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">
              Dashboard Spec (TOON format)
            </label>
            <Textarea
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              className="h-[600px] font-mono text-xs leading-relaxed"
              spellCheck={false}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-foreground">Parsed Output</label>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  spec
                    ? "bg-primary/10 text-primary"
                    : "bg-destructive/10 text-destructive"
                }`}
              >
                {spec ? `✓ ${spec.components.length} components` : "✗ Parse error"}
              </span>
            </div>
            <pre className="h-[600px] overflow-auto rounded-md border border-border bg-muted/30 p-4 text-xs">
              {spec ? JSON.stringify(spec, null, 2) : "Failed to parse dashboard spec"}
            </pre>
          </div>
        </div>

        <div className="space-y-2">
          <h2 className="text-lg font-semibold text-foreground">Rendered Preview</h2>
          {spec ? (
            <DashboardLayout spec={spec} />
          ) : (
            <div className="rounded-md border border-border bg-card p-8 text-center text-sm text-muted-foreground">
              Fix the spec above to see a preview
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
