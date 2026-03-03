export type CellFormat = "currency" | "percent" | "number" | "date" | "text";

export interface ColumnDef {
  key: string;
  label: string;
  format: CellFormat;
  sortable?: boolean;
}

export interface DataTableProps {
  type: "data-table";
  columns: ColumnDef[];
  data: Record<string, unknown>[];
  defaultSort?: { key: string; direction: "asc" | "desc" };
  searchable?: boolean;
  title?: string;
}

export interface KPICardProps {
  type: "kpi-card";
  label: string;
  value: number;
  format: CellFormat;
  delta?: number;
}

export interface LineChartProps {
  type: "line-chart";
  title: string;
  xKey: string;
  yKeys: string[];
  data: Record<string, unknown>[];
  xFormat?: CellFormat;
  yFormat?: CellFormat;
}

export interface BarChartProps {
  type: "bar-chart";
  title: string;
  categoryKey: string;
  valueKey: string;
  data: Record<string, unknown>[];
}

export interface PieChartProps {
  type: "pie-chart";
  title: string;
  labelKey: string;
  valueKey: string;
  data: Record<string, unknown>[];
}

export type DashboardComponent =
  | DataTableProps
  | KPICardProps
  | LineChartProps
  | BarChartProps
  | PieChartProps;

export interface DashboardSpec {
  title: string;
  layout: "single" | "grid-2" | "grid-3";
  components: DashboardComponent[];
}
