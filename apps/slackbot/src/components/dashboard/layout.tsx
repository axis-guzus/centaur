"use client";

import type { DashboardSpec, DashboardComponent } from "./types";
import { KPICard } from "./kpi-card";
import { DataTable } from "./data-table";
import { DashboardLineChart } from "./line-chart";
import { DashboardBarChart } from "./bar-chart";
import { DashboardPieChart } from "./pie-chart";

const GRID_CLASS: Record<DashboardSpec["layout"], string> = {
  single: "grid grid-cols-1 gap-4",
  "grid-2": "grid grid-cols-1 md:grid-cols-2 gap-4",
  "grid-3": "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
};

function renderComponent(component: DashboardComponent, index: number) {
  switch (component.type) {
    case "kpi-card":
      return (
        <KPICard
          key={index}
          label={component.label}
          value={component.value}
          format={component.format}
          delta={component.delta}
        />
      );
    case "data-table":
      return (
        <div key={index} className="col-span-full">
          <DataTable
            columns={component.columns}
            data={component.data}
            defaultSort={component.defaultSort}
            searchable={component.searchable}
            title={component.title}
          />
        </div>
      );
    case "line-chart":
      return (
        <div key={index} className="col-span-full">
          <DashboardLineChart
            title={component.title}
            xKey={component.xKey}
            yKeys={component.yKeys}
            data={component.data}
            xFormat={component.xFormat}
            yFormat={component.yFormat}
          />
        </div>
      );
    case "bar-chart":
      return (
        <DashboardBarChart
          key={index}
          title={component.title}
          categoryKey={component.categoryKey}
          valueKey={component.valueKey}
          data={component.data}
        />
      );
    case "pie-chart":
      return (
        <DashboardPieChart
          key={index}
          title={component.title}
          labelKey={component.labelKey}
          valueKey={component.valueKey}
          data={component.data}
        />
      );
    default:
      return null;
  }
}

export function DashboardLayout({ spec }: { spec: DashboardSpec }) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-foreground mb-3">{spec.title}</h2>
      <div className={GRID_CLASS[spec.layout]}>
        {spec.components.map((component, i) => renderComponent(component, i))}
      </div>
    </div>
  );
}
