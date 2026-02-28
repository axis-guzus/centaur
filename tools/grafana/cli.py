"""CLI for Grafana API."""

import json

import typer
from dotenv import load_dotenv
from rich.console import Console
from shared.cli_tables import Table

load_dotenv()

app = typer.Typer(name="grafana", help="Grafana CLI for dashboards, metrics, logs, and alerts")
console = Console()


def get_client():
    from .client import GrafanaClient

    return GrafanaClient()


@app.command("search")
def search_dashboards(
    query: str = typer.Argument(None, help="Search string"),
    tag: str = typer.Option(None, "--tag", "-t", help="Filter by tag"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Search dashboards."""
    client = get_client()
    results = client.search_dashboards(query=query, tag=tag, limit=limit)

    if json_output:
        print(json.dumps(results, indent=2))
        return

    if not results:
        console.print("[yellow]No dashboards found[/]")
        return

    table = Table(title="Dashboards")
    table.add_column("UID", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Type", style="dim")
    table.add_column("Tags", style="green")

    for d in results:
        table.add_row(
            str(d.get("uid", "")),
            str(d.get("title", "")),
            str(d.get("type", "")),
            ", ".join(d.get("tags", [])),
        )

    console.print(table)


@app.command("get")
def get_dashboard(
    uid: str = typer.Argument(..., help="Dashboard UID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Get a dashboard by UID."""
    client = get_client()
    result = client.get_dashboard(uid)

    if json_output:
        print(json.dumps(result, indent=2))
        return

    meta = result.get("meta", {})
    dash = result.get("dashboard", {})
    console.print(f"[bold]{dash.get('title', 'Untitled')}[/]")
    console.print(f"  UID: {dash.get('uid', '')}")
    console.print(f"  URL: {meta.get('url', '')}")
    console.print(f"  Version: {dash.get('version', '')}")
    panels = dash.get("panels", [])
    if panels:
        console.print(f"  Panels ({len(panels)}):")
        for p in panels:
            console.print(f"    - {p.get('title', '(untitled)')} [{p.get('type', '')}]")


@app.command("datasources")
def list_datasources(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List configured datasources."""
    client = get_client()
    results = client.list_datasources()

    if json_output:
        print(json.dumps(results, indent=2))
        return

    table = Table(title="Datasources")
    table.add_column("UID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Type", style="green")
    table.add_column("URL", style="dim")

    for ds in results:
        table.add_row(
            str(ds.get("uid", "")),
            str(ds.get("name", "")),
            str(ds.get("type", "")),
            str(ds.get("url", "")),
        )

    console.print(table)


@app.command("prom")
def query_prometheus(
    expr: str = typer.Argument(..., help="PromQL expression"),
    datasource: str = typer.Option("prometheus", "--ds", help="Datasource UID"),
    start: str = typer.Option(None, "--start", "-s", help="Range start (RFC3339 / epoch)"),
    end: str = typer.Option(None, "--end", "-e", help="Range end"),
    step: str = typer.Option("60s", "--step", help="Range query step"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Run a PromQL query via datasource proxy."""
    client = get_client()
    result = client.query_prometheus(
        expr=expr, datasource_uid=datasource, start=start, end=end, step=step
    )

    if json_output:
        print(json.dumps(result, indent=2))
        return

    data = result.get("data", {})
    results = data.get("result", [])

    if not results:
        console.print("[yellow]No results[/]")
        return

    for r in results:
        metric = r.get("metric", {})
        label = ", ".join(f"{k}={v}" for k, v in metric.items()) or "(scalar)"
        values = r.get("values") or [r.get("value", [])]
        console.print(f"[cyan]{label}[/]")
        for v in values[-5:]:
            if isinstance(v, list) and len(v) == 2:
                console.print(f"  {v[0]} → {v[1]}")


@app.command("loki")
def query_loki(
    query: str = typer.Argument(..., help="LogQL expression"),
    datasource: str = typer.Option("loki", "--ds", help="Datasource UID"),
    start: str = typer.Option(None, "--start", "-s", help="Range start"),
    end: str = typer.Option(None, "--end", "-e", help="Range end"),
    limit: int = typer.Option(100, "--limit", "-n", help="Max log lines"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Run a LogQL query via datasource proxy."""
    client = get_client()
    result = client.query_loki(
        query=query, datasource_uid=datasource, start=start, end=end, limit=limit
    )

    if json_output:
        print(json.dumps(result, indent=2))
        return

    data = result.get("data", {})
    streams = data.get("result", [])

    if not streams:
        console.print("[yellow]No results[/]")
        return

    for stream in streams:
        labels = stream.get("stream", {})
        label_str = ", ".join(f"{k}={v}" for k, v in labels.items())
        console.print(f"[cyan]--- {label_str} ---[/]")
        for ts, line in stream.get("values", [])[-20:]:
            console.print(f"  {line}")


@app.command("alerts")
def get_alerts(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List active alerts."""
    client = get_client()
    alerts = client.get_alerts()

    if json_output:
        print(json.dumps(alerts, indent=2))
        return

    if not alerts:
        console.print("[green]No active alerts[/]")
        return

    table = Table(title="Active Alerts")
    table.add_column("Name", style="red")
    table.add_column("State", style="yellow")
    table.add_column("Summary", style="white", max_width=60)

    for a in alerts:
        labels = a.get("labels", {})
        annotations = a.get("annotations", {})
        table.add_row(
            labels.get("alertname", ""),
            a.get("state", ""),
            annotations.get("summary", annotations.get("description", ""))[:60],
        )

    console.print(table)


@app.command("annotations")
def list_annotations(
    dashboard_uid: str = typer.Option(None, "--dashboard", "-d", help="Dashboard UID"),
    limit: int = typer.Option(100, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List annotations."""
    client = get_client()
    results = client.list_annotations(dashboard_uid=dashboard_uid, limit=limit)

    if json_output:
        print(json.dumps(results, indent=2))
        return

    if not results:
        console.print("[yellow]No annotations found[/]")
        return

    table = Table(title="Annotations")
    table.add_column("ID", style="dim")
    table.add_column("Text", style="white", max_width=60)
    table.add_column("Dashboard", style="cyan")
    table.add_column("Time", style="dim")

    for a in results:
        table.add_row(
            str(a.get("id", "")),
            str(a.get("text", ""))[:60],
            str(a.get("dashboardUID", "")),
            str(a.get("time", "")),
        )

    console.print(table)


@app.command()
def health():
    """Check Grafana health."""
    client = get_client()
    result = client.health()
    console.print(f"[green]Grafana: {result.get('version', '?')} — {result.get('database', '?')}[/]")


if __name__ == "__main__":
    app()
