/**
 * Convert ```dashboard fenced blocks into Slack-friendly markdown + image files.
 *
 * Dashboard blocks are a custom format for tables, KPI cards, and charts.
 * Structured clients can render them directly; Slack gets:
 *   - tables → markdown tables (later flattened to bullets if Block Kit rejects)
 *   - KPI cards → bold-prefixed inline text
 *   - charts → PNG image files attached to the same Slack message,
 *     rendered via the chart tool when a renderer is provided.
 *
 */

import { decode } from "@toon-format/toon";

const DASHBOARD_REGEX = /```dashboard\n([\s\S]*?)```/g;

type CellFormat = "currency" | "compact-currency" | "percent" | "number" | "date" | "text";

interface ColumnDef {
  key: string;
  label: string;
  format: CellFormat;
}

interface DataTableProps {
  type: "data-table";
  title?: string;
  columns: ColumnDef[];
  data: Record<string, unknown>[];
  defaultSort?: { key: string; direction: "asc" | "desc" };
}

interface KPICardProps {
  type: "kpi-card";
  label: string;
  value: number;
  format: CellFormat;
  delta?: number;
}

interface ChartProps {
  type: "line-chart" | "bar-chart" | "pie-chart";
  title: string;
  data: Record<string, unknown>[];
  [key: string]: unknown;
}

type DashboardComponent = DataTableProps | KPICardProps | ChartProps;

interface DashboardSpec {
  title: string;
  components: DashboardComponent[];
}

// ── Parsing for dashboard fenced blocks ───────────────────────────────────

function parseKeyValue(line: string): [string, string] | null {
  const idx = line.indexOf(":");
  if (idx === -1) return null;
  return [line.slice(0, idx).trim(), line.slice(idx + 1).trim()];
}

const VALID_FORMATS = new Set(["currency", "compact-currency", "percent", "number", "date", "text"]);

function parseCellFormat(raw: string): CellFormat {
  return VALID_FORMATS.has(raw) ? (raw as CellFormat) : "text";
}

function parseColumns(raw: string): ColumnDef[] {
  return raw.split(",").map((part) => {
    const trimmed = part.trim();
    const [key, fmt] = trimmed.split(":");
    return {
      key,
      label: key.charAt(0).toUpperCase() + key.slice(1),
      format: fmt ? parseCellFormat(fmt) : "text",
    };
  });
}

function dedent(raw: string): string {
  const lines = raw.split("\n");
  const indents = lines.filter((l) => l.trim().length > 0).map((l) => l.match(/^(\s*)/)![1].length);
  const min = indents.length > 0 ? Math.min(...indents) : 0;
  return min > 0 ? lines.map((l) => l.slice(min)).join("\n") : raw;
}

function decodeToonData(raw: string): Record<string, unknown>[] | null {
  const dedented = dedent(raw);

  try {
    const direct = decode(dedented, { strict: false });
    if (Array.isArray(direct) && direct.length > 0) return direct as Record<string, unknown>[];
  } catch { /* noop */ }

  try {
    const wrapped = `_:\n${dedented.split("\n").map((line) => `  ${line}`).join("\n")}`;
    const result = decode(wrapped, { strict: false });
    if (result && typeof result === "object" && "_" in result) {
      const val = (result as Record<string, unknown>)["_"];
      if (Array.isArray(val) && val.length > 0) return val as Record<string, unknown>[];
    }
  } catch { /* noop */ }

  try {
    const parsed = JSON.parse(dedented);
    if (Array.isArray(parsed)) return parsed as Record<string, unknown>[];
  } catch { /* noop */ }

  return null;
}

function parseComponentSection(section: string): DashboardComponent | null {
  const lines = section.split("\n");
  const kv: Record<string, string> = {};
  let dataBlock: string | null = null;
  let inData = false;

  for (const line of lines) {
    if (inData) {
      if (dataBlock === null) dataBlock = "";
      dataBlock += (dataBlock ? "\n" : "") + line;
      continue;
    }
    const parsed = parseKeyValue(line);
    if (!parsed) continue;
    const [key, value] = parsed;
    if (key === "data") {
      if (value) dataBlock = value;
      else inData = true;
      continue;
    }
    kv[key] = value;
  }

  const type = kv["type"];
  if (!type) return null;
  const data = dataBlock ? decodeToonData(dataBlock) : undefined;

  switch (type) {
    case "data-table": {
      if (!kv["columns"]) return null;
      const result: DataTableProps = { type: "data-table", columns: parseColumns(kv["columns"]), data: data ?? [] };
      if (kv["title"]) result.title = kv["title"];
      if (kv["defaultSort"]) {
        const [key, direction] = kv["defaultSort"].split(",").map((s) => s.trim());
        if (key && (direction === "asc" || direction === "desc")) result.defaultSort = { key, direction };
      }
      return result;
    }
    case "kpi-card": {
      if (!kv["label"] || kv["value"] === undefined) return null;
      return {
        type: "kpi-card",
        label: kv["label"],
        value: Number(kv["value"]),
        format: parseCellFormat(kv["format"] ?? "number"),
        ...(kv["delta"] !== undefined ? { delta: Number(kv["delta"]) } : {}),
      };
    }
    case "line-chart":
    case "bar-chart":
    case "pie-chart":
      return { type, title: kv["title"] || type, data: data ?? [], ...kv } as ChartProps;
    default:
      return null;
  }
}

function parseDashboardSpec(raw: string): DashboardSpec | null {
  try {
    const sections = raw.split("\n---\n");
    if (sections.length < 2) return null;

    const headerLines = sections[0].split("\n");
    const header: Record<string, string> = {};
    for (const line of headerLines) {
      const parsed = parseKeyValue(line);
      if (parsed) header[parsed[0]] = parsed[1];
    }
    if (!header["title"]) return null;

    const components: DashboardComponent[] = [];
    for (let i = 1; i < sections.length; i++) {
      const component = parseComponentSection(sections[i].trim());
      if (component) components.push(component);
    }
    if (components.length === 0) return null;

    return { title: header["title"], components };
  } catch {
    return null;
  }
}

// ── Formatting ───────────────────────────────────────────────────────────

function formatValue(value: unknown, format: CellFormat): string {
  if (value === null || value === undefined) return "";
  const num = typeof value === "number" ? value : Number(value);

  switch (format) {
    case "currency":
      if (isNaN(num)) return String(value);
      return num >= 1e9 ? `$${(num / 1e9).toFixed(2)}B`
        : num >= 1e6 ? `$${(num / 1e6).toFixed(2)}M`
        : num >= 1e3 ? `$${(num / 1e3).toFixed(1)}K`
        : `$${num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    case "compact-currency":
      if (isNaN(num)) return String(value);
      return num >= 1e9 ? `$${(num / 1e9).toFixed(1)}B`
        : num >= 1e6 ? `$${(num / 1e6).toFixed(1)}M`
        : num >= 1e3 ? `$${(num / 1e3).toFixed(0)}K`
        : `$${Math.round(num)}`;
    case "percent":
      return isNaN(num) ? String(value) : `${num.toFixed(1)}%`;
    case "number":
      return isNaN(num) ? String(value) : num.toLocaleString("en-US");
    case "date":
      return String(value);
    default:
      return String(value);
  }
}

function componentToSlackMarkdown(component: DashboardComponent): string {
  switch (component.type) {
    case "kpi-card": {
      const val = formatValue(component.value, component.format);
      const delta = component.delta !== undefined ? ` (${component.delta > 0 ? "+" : ""}${component.delta}%)` : "";
      return `*${component.label}:* ${val}${delta}`;
    }
    case "data-table": {
      const { columns, data, title, defaultSort } = component;
      if (!data.length) return title ? `*${title}*\n_No data_` : "_No data_";

      const rows = [...data];
      if (defaultSort) {
        rows.sort((a, b) => {
          const av = a[defaultSort.key], bv = b[defaultSort.key];
          const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
          return defaultSort.direction === "desc" ? -cmp : cmp;
        });
      }

      // Build a standard markdown table
      const header = `| ${columns.map((c) => c.label).join(" | ")} |`;
      const separator = `| ${columns.map(() => "---").join(" | ")} |`;
      const bodyRows = rows.map(
        (row) => `| ${columns.map((c) => formatValue(row[c.key], c.format)).join(" | ")} |`,
      );

      const parts: string[] = [];
      if (title) parts.push(`*${title}*`);
      parts.push(header, separator, ...bodyRows);
      return parts.join("\n");
    }
    case "line-chart":
    case "bar-chart":
    case "pie-chart":
      return `_${component.title} (chart — view in Thread Viewer)_`;
    default:
      return "";
  }
}

function dashboardToSlackMarkdown(spec: DashboardSpec): string {
  const parts: string[] = [`*${spec.title}*`];

  // Group KPI cards on one line, tables separately
  const kpis = spec.components.filter((c): c is KPICardProps => c.type === "kpi-card");
  const others = spec.components.filter((c) => c.type !== "kpi-card");

  if (kpis.length > 0) {
    parts.push(kpis.map((k) => componentToSlackMarkdown(k)).join("  ·  "));
  }

  for (const component of others) {
    parts.push(componentToSlackMarkdown(component));
  }

  return parts.join("\n\n");
}

// ── Public API ───────────────────────────────────────────────────────────

/**
 * Renderer that turns a chart component spec into PNG bytes.
 * Returns `null` to signal "couldn't render" so the caller falls back to
 * the placeholder string instead of dropping the chart silently.
 */
export type ChartRenderer = (chart: ChartProps) => Promise<Buffer | null>;

export interface DashboardFileUpload {
  data: Buffer;
  filename: string;
  mimeType?: string;
}

export interface DashboardConversion {
  /** Markdown with dashboard blocks expanded; chart components removed when rendered to files. */
  markdown: string;
  /** Image files (typically PNGs) to attach to the same Slack message. */
  files: DashboardFileUpload[];
}

function isChartProps(c: DashboardComponent): c is ChartProps {
  return c.type === "line-chart" || c.type === "bar-chart" || c.type === "pie-chart";
}

function chartFilenameFromTitle(title: string): string {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  return `${slug || "chart"}.png`;
}

async function replaceAsync(
  str: string,
  regex: RegExp,
  replacer: (match: string, ...groups: string[]) => Promise<string>,
): Promise<string> {
  const promises: Promise<string>[] = [];
  // Trigger replacer for every match to collect promises in order; throw away
  // the synchronous return value (the second .replace below uses the awaited
  // results in match-order).
  str.replace(regex, (match, ...args) => {
    const groups = args.slice(0, -2) as string[];
    promises.push(replacer(match, ...groups));
    return match;
  });
  const resolved = await Promise.all(promises);
  let i = 0;
  return str.replace(regex, () => resolved[i++]);
}

/**
 * Replace all ```dashboard blocks in markdown with Slack-friendly equivalents.
 *
 * When `options.renderChart` is provided, chart components are rendered to
 * PNG and returned in `files`; the markdown is left without a placeholder
 * for those charts so the same Slack message gets them attached natively.
 *
 * When `renderChart` is missing or returns null, charts fall back to the
 * "_<title> (chart — view in Thread Viewer)_" placeholder so the user at
 * least sees what was attempted.
 */
export async function convertDashboardBlocks(
  markdown: string,
  options?: { renderChart?: ChartRenderer },
): Promise<DashboardConversion> {
  const files: DashboardFileUpload[] = [];

  const newMarkdown = await replaceAsync(
    markdown,
    DASHBOARD_REGEX,
    async (raw, content) => {
      const spec = parseDashboardSpec(content);
      if (!spec) return raw;

      // Render charts to PNGs. Only successful renders are removed from
      // the dashboard spec; failed renders fall through to the placeholder
      // path inside componentToSlackMarkdown so the user can see something
      // was meant to be there.
      const renderedCharts = new Set<ChartProps>();
      if (options?.renderChart) {
        for (const c of spec.components) {
          if (!isChartProps(c)) continue;
          try {
            const buf = await options.renderChart(c);
            if (buf && buf.length > 0) {
              files.push({
                data: buf,
                filename: chartFilenameFromTitle(c.title),
                mimeType: "image/png",
              });
              renderedCharts.add(c);
            }
          } catch {
            // best-effort; placeholder string is shown instead
          }
        }
      }

      const remainingComponents = spec.components.filter(
        (c) => !(isChartProps(c) && renderedCharts.has(c)),
      );
      if (remainingComponents.length === 0 && renderedCharts.size > 0) {
        // Charts-only dashboard, all rendered: leave a tiny title anchor so
        // the file uploads are introduced by the dashboard's heading.
        return spec.title ? `*${spec.title}*` : "";
      }
      return dashboardToSlackMarkdown({ ...spec, components: remainingComponents });
    },
  );

  return { markdown: newMarkdown, files };
}
