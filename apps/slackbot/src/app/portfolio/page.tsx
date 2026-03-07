"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { RenderNode } from "@/components/dashboard/component-renderer";
import type { ComponentNode, ColumnDef } from "@/components/dashboard/types";
import ReactGridLayout, { useContainerWidth, verticalCompactor } from "react-grid-layout";
import type { Layout, LayoutItem } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import {
  Loader2Icon,
  AlertCircleIcon,
  Pencil,
  Eye,
  Plus,
  X,
  BarChart3,
  Table,
  PieChart,
  LineChart,
  LayoutGrid,
  Lock,
  Unlock,
  RotateCcw,
} from "lucide-react";

// ── Types ──

interface Position {
  assetName: string;
  ticker: string | null;
  marketValue: number;
  grossInvestedCapital: number;
  moic: number;
  holding: number;
  fundName: string;
  realizedGainLoss: number;
  [key: string]: unknown;
}

// ── Palette ──

type PaletteItem = {
  id: string;
  label: string;
  icon: React.ElementType;
  description: string;
  buildNode: (positions: Position[]) => ComponentNode;
};

function buildKPINodes(positions: Position[]): {
  totalMV: number;
  totalIC: number;
  count: number;
  avgMoic: number;
  totalGL: number;
} {
  const totalMV = positions.reduce((s, p) => s + (p.marketValue ?? 0), 0);
  const totalIC = positions.reduce((s, p) => s + (p.grossInvestedCapital ?? 0), 0);
  const count = positions.length;
  const moics = positions.filter((p) => p.moic != null && p.moic > 0);
  const avgMoic = moics.length > 0 ? moics.reduce((s, p) => s + p.moic, 0) / moics.length : 0;
  const totalGL = positions.reduce((s, p) => s + (p.realizedGainLoss ?? 0), 0);
  return { totalMV, totalIC, count, avgMoic, totalGL };
}

const POSITIONS_COLUMNS: ColumnDef[] = [
  {
    key: "assetName",
    label: "Asset",
    format: "text",
    sortable: true,
    cell: { type: "stacked-text", secondaryKey: "ticker" },
  },
  {
    key: "fundName",
    label: "Fund",
    format: "text",
    filterable: true,
    cell: { type: "badge", intentMap: {
      "Paradigm Fund LP": "default",
      "Paradigm One LP": "success",
      "Paradigm Two LP": "outline",
      "Paradigm Three LP": "warning",
      "Paradigm Green Fortitudo LP": "success",
    } },
  },
  { key: "marketValue", label: "Market Value", format: "compact-currency", sortable: true, align: "right" },
  { key: "grossInvestedCapital", label: "Invested Capital", format: "compact-currency", sortable: true, align: "right" },
  { key: "moic", label: "MOIC", format: "number", sortable: true, align: "right" },
  { key: "realizedGainLoss", label: "Realized G/L", format: "compact-currency", sortable: true, align: "right" },
];

function buildPalette(): PaletteItem[] {
  return [
    {
      id: "kpi-mv",
      label: "Market Value",
      icon: BarChart3,
      description: "Total portfolio market value",
      buildNode: (pos) => ({
        type: "kpi-card",
        label: "Total Market Value",
        value: buildKPINodes(pos).totalMV,
        format: "compact-currency",
      }),
    },
    {
      id: "kpi-ic",
      label: "Invested Capital",
      icon: BarChart3,
      description: "Total invested capital",
      buildNode: (pos) => ({
        type: "kpi-card",
        label: "Invested Capital",
        value: buildKPINodes(pos).totalIC,
        format: "compact-currency",
      }),
    },
    {
      id: "kpi-count",
      label: "Position Count",
      icon: LayoutGrid,
      description: "Number of active positions",
      buildNode: (pos) => ({
        type: "kpi-card",
        label: "Positions",
        value: buildKPINodes(pos).count,
        format: "number",
      }),
    },
    {
      id: "kpi-moic",
      label: "Avg MOIC",
      icon: LineChart,
      description: "Average MOIC across positions",
      buildNode: (pos) => ({
        type: "kpi-card",
        label: "Avg MOIC",
        value: Math.round(buildKPINodes(pos).avgMoic * 100) / 100,
        format: "number",
      }),
    },
    {
      id: "table-positions",
      label: "Positions Table",
      icon: Table,
      description: "Full positions table with sort & filter",
      buildNode: (pos) => ({
        type: "data-table",
        title: "Positions",
        searchable: true,
        columns: POSITIONS_COLUMNS,
        data: pos.map((p) => ({
          ...p,
          moic: p.moic != null ? Math.round(p.moic * 100) / 100 : null,
        })),
        defaultSort: { key: "marketValue", direction: "desc" },
        pageSize: 50,
      }),
    },
    {
      id: "pie-fund",
      label: "Fund Allocation",
      icon: PieChart,
      description: "Market value breakdown by fund",
      buildNode: (pos) => {
        const byFund = new Map<string, number>();
        for (const p of pos) {
          const f = p.fundName || "Unknown";
          byFund.set(f, (byFund.get(f) ?? 0) + (p.marketValue ?? 0));
        }
        return {
          type: "pie-chart",
          title: "Allocation by Fund",
          labelKey: "fund",
          valueKey: "value",
          height: 300,
          data: [...byFund.entries()]
            .sort((a, b) => b[1] - a[1])
            .map(([fund, value]) => ({ fund, value })),
        };
      },
    },
    {
      id: "pie-top-assets",
      label: "Top Assets Pie",
      icon: PieChart,
      description: "Top 10 assets by market value",
      buildNode: (pos) => {
        const sorted = [...pos].sort((a, b) => (b.marketValue ?? 0) - (a.marketValue ?? 0));
        const top = sorted.slice(0, 10);
        const rest = sorted.slice(10).reduce((s, p) => s + (p.marketValue ?? 0), 0);
        const data = top.map((p) => ({
          name: p.assetName || p.ticker || "Unknown",
          value: p.marketValue,
        }));
        if (rest > 0) data.push({ name: "Other", value: rest });
        return {
          type: "pie-chart",
          title: "Top Holdings",
          labelKey: "name",
          valueKey: "value",
          height: 300,
          data,
        };
      },
    },
    {
      id: "bar-fund-mv",
      label: "Fund Bar Chart",
      icon: BarChart3,
      description: "Market value by fund",
      buildNode: (pos) => {
        const byFund = new Map<string, number>();
        for (const p of pos) {
          const f = p.fundName || "Unknown";
          byFund.set(f, (byFund.get(f) ?? 0) + (p.marketValue ?? 0));
        }
        return {
          type: "bar-chart",
          title: "AUM by Fund",
          categoryKey: "fund",
          valueKey: "value",
          height: 280,
          data: [...byFund.entries()]
            .sort((a, b) => b[1] - a[1])
            .map(([fund, value]) => ({ fund, value })),
        };
      },
    },
  ];
}

// ── Grid Layout ──

type CanvasItem = { instanceId: string; paletteId: string; node: ComponentNode };

const GRID_COLS = 12;
const GRID_ROW_HEIGHT = 60;

function defaultGridSize(node: ComponentNode): { w: number; h: number } {
  switch (node.type) {
    case "kpi-card": return { w: 3, h: 2 };
    case "data-table": return { w: 12, h: 7 };
    case "line-chart": return { w: 6, h: 5 };
    case "bar-chart": return { w: 6, h: 5 };
    case "pie-chart": return { w: 6, h: 5 };
    default: return { w: 4, h: 3 };
  }
}

function buildGridLayout(items: { instanceId: string; node: ComponentNode }[]): Layout {
  const result: LayoutItem[] = [];
  let x = 0;
  let y = 0;
  let rowMaxH = 0;
  for (const item of items) {
    const { w, h } = defaultGridSize(item.node);
    if (x + w > GRID_COLS) { x = 0; y += rowMaxH; rowMaxH = 0; }
    result.push({ i: item.instanceId, x, y, w, h, minW: 2, minH: 1 });
    x += w;
    rowMaxH = Math.max(rowMaxH, h);
  }
  return result;
}

// ── Default dashboard ──

const DEFAULT_PALETTE_IDS = [
  "kpi-mv",
  "kpi-ic",
  "kpi-count",
  "kpi-moic",
  "table-positions",
  "pie-fund",
  "pie-top-assets",
];

function buildDefaultCanvas(positions: Position[], palette: PaletteItem[]): CanvasItem[] {
  return DEFAULT_PALETTE_IDS.map((id, i) => {
    const item = palette.find((p) => p.id === id)!;
    return {
      instanceId: `default-${i}`,
      paletteId: id,
      node: item.buildNode(positions),
    };
  });
}

// ── Page ──

export default function PortfolioPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [locked, setLocked] = useState(true);

  const palette = useMemo(() => buildPalette(), []);

  // Canvas state
  const [canvas, setCanvas] = useState<CanvasItem[]>([]);
  const [gridLayout, setGridLayout] = useState<Layout>([]);
  const [counter, setCounter] = useState(100);

  // react-grid-layout
  const { width: rglWidth, containerRef: rglRef, mounted: rglMounted } = useContainerWidth();

  // Load data
  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/portfolio/positions?limit=500");
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        const data = await res.json();
        const raw = data.result;
        if (!raw || (typeof raw === "object" && "error" in raw)) {
          throw new Error(typeof raw?.error === "string" ? raw.error : "No position data");
        }
        const arr: Position[] = Array.isArray(raw) ? raw : [];
        setPositions(arr);

        // Build default dashboard
        const pal = buildPalette();
        const defaultItems = buildDefaultCanvas(arr, pal);
        setCanvas(defaultItems);
        setGridLayout(buildGridLayout(defaultItems));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load portfolio data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const addComponent = useCallback(
    (item: PaletteItem) => {
      if (!editing || locked) {
        toast("Switch to edit mode and unlock first");
        return;
      }
      const id = `item-${counter}`;
      const node = item.buildNode(positions);
      setCanvas((prev) => [...prev, { instanceId: id, paletteId: item.id, node }]);
      setGridLayout((prev) => {
        const { w, h } = defaultGridSize(node);
        const maxY = prev.reduce((m, l) => Math.max(m, l.y + l.h), 0);
        return [...prev, { i: id, x: 0, y: maxY, w, h, minW: 2, minH: 1 }];
      });
      setCounter((c) => c + 1);
      toast(`Added "${item.label}"`);
    },
    [counter, editing, locked, positions],
  );

  const removeComponent = useCallback(
    (instanceId: string) => {
      if (!editing || locked) return;
      setCanvas((prev) => prev.filter((c) => c.instanceId !== instanceId));
      setGridLayout((prev) => prev.filter((l) => l.i !== instanceId));
    },
    [editing, locked],
  );

  const resetDashboard = useCallback(() => {
    const defaultItems = buildDefaultCanvas(positions, palette);
    setCanvas(defaultItems);
    setGridLayout(buildGridLayout(defaultItems));
    toast("Dashboard reset to default");
  }, [positions, palette]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2Icon className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-center">
          <AlertCircleIcon className="size-8 text-destructive" />
          <p className="text-sm text-muted-foreground">{error}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-md bg-secondary px-3 py-1.5 text-xs font-medium text-foreground hover:bg-secondary/80"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1600px] px-6 py-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Portfolio</h1>
        <div className="flex items-center gap-2">
          {editing && (
            <>
              <Button
                variant="ghost"
                size="xs"
                className="gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                onClick={resetDashboard}
              >
                <RotateCcw className="size-3" />
                Reset
              </Button>
              <Separator orientation="vertical" className="h-5" />
              <Button
                variant={locked ? "default" : "outline"}
                size="xs"
                onClick={() => {
                  setLocked((v) => !v);
                  toast(locked ? "Canvas unlocked — drag & resize" : "Canvas locked");
                }}
                className={`gap-1.5 text-xs ${locked ? "bg-primary text-primary-foreground" : ""}`}
              >
                {locked ? <Lock className="size-3" /> : <Unlock className="size-3" />}
                {locked ? "Locked" : "Unlocked"}
              </Button>
              <Separator orientation="vertical" className="h-5" />
            </>
          )}
          <Button
            variant={editing ? "default" : "outline"}
            size="xs"
            onClick={() => {
              setEditing((v) => {
                if (v) setLocked(true); // lock when exiting edit
                return !v;
              });
            }}
            className={`gap-1.5 text-xs ${editing ? "bg-primary text-primary-foreground" : ""}`}
          >
            {editing ? <Eye className="size-3" /> : <Pencil className="size-3" />}
            {editing ? "Done" : "Edit"}
          </Button>
        </div>
      </div>

      {editing ? (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_1fr]">
          {/* Palette */}
          <aside className="space-y-2">
            <h3 className="text-sm font-medium text-foreground">Components</h3>
            <div className="thin-scrollbar max-h-[700px] space-y-1 overflow-y-auto pr-1">
              {palette.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => addComponent(item)}
                    className="group flex w-full items-center gap-2.5 rounded-lg border border-border/50 bg-card/30 px-2.5 py-2 text-left transition-colors hover:border-primary/40 hover:bg-primary/5"
                  >
                    <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted/50 text-muted-foreground transition-colors group-hover:bg-primary/10 group-hover:text-primary">
                      <Icon className="size-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-foreground">{item.label}</div>
                      <div className="truncate text-xs text-muted-foreground">{item.description}</div>
                    </div>
                    <Plus className="size-3.5 shrink-0 text-muted-foreground/50 transition-colors group-hover:text-primary" />
                  </button>
                );
              })}
            </div>
          </aside>

          {/* Canvas */}
          <div>
            {canvas.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-border/60 bg-card/20 py-20 text-center">
                <LayoutGrid className="mb-3 size-8 text-muted-foreground/40" />
                <p className="text-sm font-medium text-muted-foreground">No components</p>
                <p className="mt-1 text-xs text-muted-foreground/70">
                  Click items in the palette to add them
                </p>
              </div>
            ) : (
              <div
                ref={rglRef}
                className="rounded-lg border border-border/60 bg-card/20 p-4"
                style={{ position: "relative" }}
              >
                {rglMounted && (
                  <ReactGridLayout
                    layout={gridLayout.map((l) => ({ ...l, static: locked }))}
                    width={rglWidth - 32}
                    gridConfig={{ cols: GRID_COLS, rowHeight: GRID_ROW_HEIGHT, margin: [12, 12] }}
                    dragConfig={{ enabled: !locked }}
                    resizeConfig={{ enabled: !locked, handles: ["se"] }}
                    compactor={verticalCompactor}
                    onLayoutChange={(newLayout) => {
                      if (!locked) setGridLayout(newLayout as Layout);
                    }}
                  >
                    {canvas.map((item) => (
                      <div
                        key={item.instanceId}
                        className={`group/grid-item overflow-hidden rounded-lg border bg-card/40 ${
                          locked
                            ? "border-border/30"
                            : "border-border/60 hover:border-primary/40"
                        }`}
                      >
                        {!locked && (
                          <button
                            type="button"
                            onClick={() => removeComponent(item.instanceId)}
                            className="absolute right-1.5 top-1.5 z-10 flex size-5 items-center justify-center rounded-full bg-destructive/80 text-destructive-foreground opacity-0 transition-opacity hover:bg-destructive group-hover/grid-item:opacity-100"
                          >
                            <X className="size-3" />
                          </button>
                        )}
                        <div className="size-full overflow-auto p-2">
                          <RenderNode node={item.node} />
                        </div>
                      </div>
                    ))}
                  </ReactGridLayout>
                )}
              </div>
            )}
          </div>
        </div>
      ) : (
        /* View mode — render grid layout without palette */
        <div
          ref={rglRef}
          style={{ position: "relative" }}
        >
          {canvas.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-border/60 bg-card/20 py-20 text-center">
              <LayoutGrid className="mb-3 size-8 text-muted-foreground/40" />
              <p className="text-sm font-medium text-muted-foreground">No components</p>
              <p className="mt-1 text-xs text-muted-foreground/70">
                Click Edit to build your dashboard
              </p>
            </div>
          ) : rglMounted ? (
            <ReactGridLayout
              layout={gridLayout.map((l) => ({ ...l, static: true }))}
              width={rglWidth}
              gridConfig={{ cols: GRID_COLS, rowHeight: GRID_ROW_HEIGHT, margin: [12, 12] }}
              dragConfig={{ enabled: false }}
              resizeConfig={{ enabled: false }}
              compactor={verticalCompactor}
            >
              {canvas.map((item) => (
                <div
                  key={item.instanceId}
                  className="overflow-hidden rounded-lg border border-border/30 bg-card/40"
                >
                  <div className="size-full overflow-auto p-2">
                    <RenderNode node={item.node} />
                  </div>
                </div>
              ))}
            </ReactGridLayout>
          ) : null}
        </div>
      )}
    </div>
  );
}
