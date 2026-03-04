"""CLI for term sheet generation and deal tracking."""

import json
from enum import StrEnum
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

from shared.cli_tables import Table

from .client import TermsheetClient
from .models import BoardRights, DealStatus, InstrumentType, TermIntent, TokenRights

load_dotenv()

app = typer.Typer(help="Term sheet generation and deal tracking for Paradigm")
console = Console()
client = TermsheetClient()


class CreateOutputFormat(StrEnum):
    TEXT = "text"
    DOCX = "docx"
    JSON = "json"


class ListOutputFormat(StrEnum):
    TABLE = "table"
    JSON = "json"


class GetOutputFormat(StrEnum):
    TEXT = "text"
    DOCX = "docx"
    JSON = "json"
    EMAIL = "email"


def _format_money(amount: float) -> str:
    if amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.1f}B"
    elif amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    elif amount >= 1_000:
        return f"${amount / 1_000:.0f}K"
    else:
        return f"${amount:,.0f}"


def _status_emoji(status: DealStatus) -> str:
    return {
        DealStatus.DRAFT: "📝",
        DealStatus.PENDING_APPROVAL: "⏳",
        DealStatus.APPROVED: "✅",
        DealStatus.SENT: "📤",
    }.get(status, "❓")


def _resolve_template_file(template_file: str | None) -> Path | None:
    if not template_file:
        return None
    path = Path(template_file).expanduser().resolve()
    if not path.exists():
        console.print(f"[red]Template file not found: {path}[/red]")
        raise typer.Exit(1)
    return path


@app.command("create")
def create_term_sheet(
    company: str = typer.Argument(..., help="Company name"),
    amount: float = typer.Option(..., "--amount", "-a", help="Investment amount in USD"),
    instrument: str = typer.Option(
        "priced", "--instrument", "-i", help="Instrument type: safe, priced, convertible_note"
    ),
    valuation_cap: float | None = typer.Option(
        None, "--cap", help="Valuation cap (for SAFE/convertible)"
    ),
    discount: float | None = typer.Option(
        None, "--discount", help="Discount percentage (for SAFE/convertible)"
    ),
    pre_money: float | None = typer.Option(
        None, "--pre-money", help="Pre-money valuation (for priced rounds)"
    ),
    post_money: float | None = typer.Option(
        None, "--post-money", help="Post-money valuation (for priced rounds)"
    ),
    series: str | None = typer.Option(None, "--series", "-s", help="Series name (A, B, C, Seed)"),
    option_pool: float = typer.Option(10.0, "--option-pool", help="Option pool percentage"),
    board: str = typer.Option(
        "observer", "--board", "-b", help="Board rights: seat, observer, seat_and_observer, none"
    ),
    intent: str = typer.Option(
        "balanced",
        "--intent",
        help="Deal intent profile: balanced, founder_friendly, investor_protective, token_heavy",
    ),
    pro_rata: bool = typer.Option(True, "--pro-rata/--no-pro-rata", help="Include pro rata rights"),
    tokens: bool = typer.Option(False, "--tokens/--no-tokens", help="Include token rights"),
    token_floor: float = typer.Option(50.0, "--token-floor", help="Token floor percentage"),
    legal_fee_cap: float = typer.Option(75000.0, "--legal-fee", help="Legal fee cap"),
    exclusivity: int = typer.Option(45, "--exclusivity", help="Exclusivity period in days"),
    debt_threshold: float | None = typer.Option(None, "--debt-threshold", help="Debt threshold"),
    ipo_threshold: float | None = typer.Option(
        None, "--ipo-threshold", help="Qualified IPO proceeds threshold"
    ),
    founder_carveout: float | None = typer.Option(
        None, "--founder-carveout", help="Founder carveout percentage in ROFR carveout"
    ),
    nvca_year: int = typer.Option(2025, "--nvca-year", help="NVCA forms reference year"),
    custom_terms: str | None = typer.Option(None, "--custom", help="Custom terms"),
    founder: str | None = typer.Option(None, "--founder", help="Founder name"),
    co_investor_text: str | None = typer.Option(
        None, "--co-investor-text", help="Override co-investor sentence in investment section"
    ),
    other_rights_text: str | None = typer.Option(
        None, "--other-rights-text", help="Override entire Other Rights section"
    ),
    token_rights_text: str | None = typer.Option(
        None, "--token-rights-text", help="Override entire Token Rights section"
    ),
    vesting_text: str | None = typer.Option(
        None, "--vesting-text", help="Override vesting language"
    ),
    protective_v_text: str | None = typer.Option(
        None, "--protective-v-text", help="Override protective provision item (v) text"
    ),
    requester_id: str = typer.Option("", "--requester-id", help="Slack user ID of requester"),
    requester_name: str = typer.Option("", "--requester-name", help="Slack username of requester"),
    slack_channel: str = typer.Option("", "--slack-channel", help="Slack channel ID"),
    slack_thread: str = typer.Option("", "--slack-thread", help="Slack thread timestamp"),
    output_format: str = typer.Option(
        "text", "--format", "-f", help="Output format: text, docx, json"
    ),
    output_file: str | None = typer.Option(None, "--output", "-o", help="Output file path"),
    template_file: str | None = typer.Option(
        None,
        "--template",
        "-t",
        help="Path to .docx template file to fill",
    ),
    save_deal: bool = typer.Option(False, "--save", help="Save as a deal for tracking"),
):
    """Create a new term sheet."""
    if save_deal and not requester_id.strip():
        console.print("[red]`--save` requires `--requester-id`[/red]")
        raise typer.Exit(1)

    resolved_template = _resolve_template_file(template_file)

    try:
        instrument_type = InstrumentType(instrument.lower())
    except ValueError as err:
        console.print(f"[red]Invalid instrument type: {instrument}[/red]")
        console.print("Valid types: safe, priced, convertible_note")
        raise typer.Exit(1) from err

    try:
        board_rights = BoardRights(board.lower())
    except ValueError as err:
        console.print(f"[red]Invalid board rights: {board}[/red]")
        console.print("Valid types: seat, observer, seat_and_observer, none")
        raise typer.Exit(1) from err

    token_rights = TokenRights(
        enabled=tokens,
        token_floor_percent=token_floor,
    )

    try:
        term_intent = TermIntent(intent.lower())
    except ValueError as err:
        console.print(f"[red]Invalid intent profile: {intent}[/red]")
        console.print("Valid types: balanced, founder_friendly, investor_protective, token_heavy")
        raise typer.Exit(1) from err

    try:
        create_format = CreateOutputFormat(output_format.lower())
    except ValueError as err:
        console.print(f"[red]Invalid output format: {output_format}[/red]")
        console.print("Valid formats: text, docx, json")
        raise typer.Exit(1) from err

    payload = {
        "company_name": company,
        "investment_amount": amount,
        "instrument_type": instrument_type,
        "valuation_cap": valuation_cap,
        "discount_percent": discount,
        "pre_money_valuation": pre_money,
        "post_money_valuation": post_money,
        "series": series,
        "option_pool_percent": option_pool,
        "board_rights": board_rights,
        "intent": term_intent,
        "pro_rata_rights": pro_rata,
        "token_rights": token_rights,
        "legal_fee_cap": legal_fee_cap,
        "nvca_year": nvca_year,
        "exclusivity_days": exclusivity,
        "custom_terms": custom_terms or "",
        "founder_name": founder or "",
        "co_investor_text": co_investor_text,
        "other_rights_text": other_rights_text,
        "token_rights_text": token_rights_text,
        "vesting_text": vesting_text,
        "protective_provision_v_text": protective_v_text,
    }
    if debt_threshold is not None:
        payload["debt_threshold"] = debt_threshold
    if ipo_threshold is not None:
        payload["ipo_threshold"] = ipo_threshold
    if founder_carveout is not None:
        payload["founder_carveout_percent"] = founder_carveout

    term_sheet = client.create_term_sheet(**payload)

    if save_deal and requester_id:
        deal = client.create_deal(
            company_name=company,
            term_sheet=term_sheet,
            requester_user_id=requester_id,
            requester_user_name=requester_name,
            slack_channel=slack_channel,
            slack_thread_ts=slack_thread,
        )
        console.print(f"[green]Created deal: {deal.id}[/green]")

    if create_format == CreateOutputFormat.TEXT:
        text = client.generate_text(term_sheet)
        if output_file:
            Path(output_file).write_text(text)
            console.print(f"[green]Saved to {output_file}[/green]")
        else:
            console.print(text)

    elif create_format == CreateOutputFormat.DOCX:
        docx_bytes = client.generate_docx(
            term_sheet,
            template_file=str(resolved_template) if resolved_template else None,
        )
        if resolved_template:
            console.print(f"[blue]Using template: {resolved_template}[/blue]")
        output_path = output_file or f"{company.replace(' ', '_')}_Term_Sheet.docx"
        Path(output_path).write_bytes(docx_bytes)
        console.print(f"[green]Saved to {output_path}[/green]")

    elif create_format == CreateOutputFormat.JSON:
        data = term_sheet.to_dict()
        if output_file:
            Path(output_file).write_text(json.dumps(data, indent=2))
            console.print(f"[green]Saved to {output_file}[/green]")
        else:
            console.print(json.dumps(data, indent=2))


@app.command("list")
def list_term_sheets(
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status"),
    output_format: str = typer.Option("table", "--format", "-f", help="Output format: table, json"),
):
    """List all tracked deals."""
    status_filter = None
    if status:
        try:
            status_filter = DealStatus(status.lower())
        except ValueError as err:
            console.print(f"[red]Invalid status: {status}[/red]")
            console.print("Valid statuses: draft, pending_approval, approved, sent")
            raise typer.Exit(1) from err

    try:
        list_format = ListOutputFormat(output_format.lower())
    except ValueError as err:
        console.print(f"[red]Invalid output format: {output_format}[/red]")
        console.print("Valid formats: table, json")
        raise typer.Exit(1) from err

    deals = client.list_deals(status_filter)

    if not deals:
        console.print("[yellow]No deals found[/yellow]")
        return

    if list_format == ListOutputFormat.JSON:
        console.print(json.dumps([d.to_dict() for d in deals], indent=2))
        return

    table = Table(title="Term Sheet Deals")
    table.add_column("ID", style="cyan")
    table.add_column("Company", style="bold")
    table.add_column("Amount")
    table.add_column("Instrument")
    table.add_column("Status")
    table.add_column("Requester")
    table.add_column("Updated")

    for deal in deals:
        ts = deal.term_sheet
        table.add_row(
            deal.id,
            deal.company_name,
            _format_money(ts.investment_amount),
            ts.instrument_type.value,
            f"{_status_emoji(deal.status)} {deal.status.value}",
            deal.requester_user_name or deal.requester_user_id,
            deal.updated_at[:10],
        )

    console.print(table)


@app.command("get")
def get_term_sheet(
    identifier: str = typer.Argument(..., help="Deal ID or company name"),
    output_format: str = typer.Option(
        "text", "--format", "-f", help="Output format: text, docx, json, email"
    ),
    output_file: str | None = typer.Option(None, "--output", "-o", help="Output file path"),
    template_file: str | None = typer.Option(
        None,
        "--template",
        "-t",
        help="Optional .docx template override for document export",
    ),
):
    """Get a specific deal by ID or company name."""
    deal = client.get_deal(identifier)

    if not deal:
        console.print(f"[red]Deal not found: {identifier}[/red]")
        raise typer.Exit(1)

    resolved_template = _resolve_template_file(template_file)
    try:
        get_format = GetOutputFormat(output_format.lower())
    except ValueError as err:
        console.print(f"[red]Invalid output format: {output_format}[/red]")
        console.print("Valid formats: text, docx, json, email")
        raise typer.Exit(1) from err

    if get_format == GetOutputFormat.JSON:
        console.print(json.dumps(deal.to_dict(), indent=2))

    elif get_format == GetOutputFormat.EMAIL:
        email = client.generate_email(deal.term_sheet)
        console.print(email)

    elif get_format == GetOutputFormat.DOCX:
        docx_bytes = client.generate_docx(
            deal.term_sheet,
            template_file=str(resolved_template) if resolved_template else None,
        )
        output_path = output_file or f"{deal.company_name.replace(' ', '_')}_Term_Sheet.docx"
        Path(output_path).write_bytes(docx_bytes)
        console.print(f"[green]Saved to {output_path}[/green]")

    else:
        console.print(f"[bold]Deal: {deal.id}[/bold]")
        console.print(f"Status: {_status_emoji(deal.status)} {deal.status.value}")
        console.print(f"Requester: {deal.requester_user_name} ({deal.requester_user_id})")
        console.print(f"Created: {deal.created_at}")
        console.print(f"Updated: {deal.updated_at}")
        if deal.approved_at:
            console.print(f"Approved: {deal.approved_at} by {deal.approved_by}")
        if deal.sent_at:
            console.print(f"Sent: {deal.sent_at}")
        console.print()
        console.print(client.generate_text(deal.term_sheet))


@app.command("package")
def package_term_sheet(
    identifier: str = typer.Argument(..., help="Deal ID or company name"),
    output_dir: str = typer.Option(".", "--output-dir", "-o", help="Directory for generated artifacts"),
    previous_docx: str | None = typer.Option(
        None, "--previous-docx", help="Optional previous clean DOCX for redline generation"
    ),
    include_pdf: bool = typer.Option(
        True, "--include-pdf/--no-include-pdf", help="Include PDF conversion artifacts"
    ),
    slack_channel: str | None = typer.Option(
        None, "--slack-channel", help="Slack channel for delivery preflight metadata"
    ),
    slack_thread: str | None = typer.Option(
        None, "--slack-thread", help="Slack thread timestamp for delivery preflight metadata"
    ),
    upload_to_slack: bool = typer.Option(
        False, "--upload-to-slack", help="Upload generated artifacts to Slack after packaging"
    ),
):
    """Generate full document package + delivery manifest for an existing deal."""
    deal = client.get_deal(identifier)
    if not deal:
        console.print(f"[red]Deal not found: {identifier}[/red]")
        raise typer.Exit(1)

    artifacts = client.generate_document_package(
        deal.term_sheet,
        output_dir=output_dir,
        previous_docx_file=previous_docx,
        include_pdf=include_pdf,
        write_manifest=True,
        slack_channel=slack_channel,
        slack_thread_ts=slack_thread,
    )
    console.print(f"[green]Package generated for {deal.company_name}[/green]")
    for key, value in artifacts.items():
        console.print(f"{key}: {value}")

    if upload_to_slack:
        if not slack_channel:
            console.print("[red]`--upload-to-slack` requires `--slack-channel`[/red]")
            raise typer.Exit(1)
        try:
            from tools.slack.client import upload_file as slack_upload_file
        except Exception as exc:
            console.print(f"[red]Slack upload tooling unavailable: {exc}[/red]")
            raise typer.Exit(1) from exc

        upload_results: list[tuple[str, str]] = []
        for artifact_key in ("clean_docx", "redline_docx", "clean_pdf", "redline_pdf"):
            artifact_path = artifacts.get(artifact_key)
            if not isinstance(artifact_path, str):
                continue
            upload = slack_upload_file(
                channel=slack_channel,
                file_path=artifact_path,
                title=Path(artifact_path).name,
                thread_ts=slack_thread,
            )
            permalink = str(upload.get("permalink", ""))
            upload_results.append((artifact_key, permalink))
        if not upload_results:
            console.print("[yellow]No package files were uploaded (no artifacts produced).[/yellow]")
        else:
            console.print("[green]Uploaded artifacts to Slack:[/green]")
            for artifact_key, permalink in upload_results:
                console.print(f"- {artifact_key}: {permalink}")


@app.command("status")
def check_status(
    company: str = typer.Argument(..., help="Company name to check status"),
):
    """Check the status of a deal by company name."""
    deal = client.get_deal(company)

    if not deal:
        console.print(f"[yellow]No deal found for: {company}[/yellow]")
        raise typer.Exit(1)

    status_text = {
        DealStatus.DRAFT: "Draft - being prepared",
        DealStatus.PENDING_APPROVAL: "Pending approval from @ben",
        DealStatus.APPROVED: "Approved - ready to send",
        DealStatus.SENT: "Sent to company",
    }.get(deal.status, deal.status.value)

    console.print(f"[bold]{deal.company_name}[/bold] ({deal.id})")
    console.print(f"Status: {_status_emoji(deal.status)} {status_text}")
    console.print(f"Requester: {deal.requester_user_name}")
    console.print(f"Amount: {_format_money(deal.term_sheet.investment_amount)}")
    console.print(f"Instrument: {deal.term_sheet.instrument_type.value}")

    if deal.revision_history:
        console.print("\n[bold]Revision History:[/bold]")
        for rev in deal.revision_history:
            console.print(f"  • {rev['timestamp'][:10]}: {rev['note']}")


@app.command("update")
def update_term_sheet(
    deal_id: str = typer.Argument(..., help="Deal ID"),
    status: str | None = typer.Option(None, "--status", "-s", help="New status"),
    approved_by: str | None = typer.Option(None, "--approved-by", help="Approver username"),
    note: str | None = typer.Option(None, "--note", "-n", help="Revision note"),
    amount: float | None = typer.Option(None, "--amount", "-a", help="Update investment amount"),
    valuation_cap: float | None = typer.Option(None, "--cap", help="Update valuation cap"),
    post_money: float | None = typer.Option(None, "--post-money", help="Update post-money"),
    board: str | None = typer.Option(None, "--board", help="Update board rights"),
    tokens: bool | None = typer.Option(None, "--tokens/--no-tokens", help="Update token rights"),
    token_floor: float | None = typer.Option(None, "--token-floor", help="Update token floor"),
):
    """Update an existing deal."""
    deal = client.get_deal(deal_id)
    if not deal:
        console.print(f"[red]Deal not found: {deal_id}[/red]")
        raise typer.Exit(1)

    new_status = None
    if status:
        try:
            new_status = DealStatus(status.lower())
        except ValueError as err:
            console.print(f"[red]Invalid status: {status}[/red]")
            raise typer.Exit(1) from err

    new_term_sheet = None
    ts = deal.term_sheet
    updated = False

    if amount is not None:
        ts.investment_amount = amount
        updated = True
    if valuation_cap is not None:
        ts.valuation_cap = valuation_cap
        updated = True
    if post_money is not None:
        ts.post_money_valuation = post_money
        updated = True
    if board is not None:
        try:
            ts.board_rights = BoardRights(board.lower())
            updated = True
        except ValueError as err:
            console.print(f"[red]Invalid board rights: {board}[/red]")
            raise typer.Exit(1) from err
    if tokens is not None:
        ts.token_rights.enabled = tokens
        updated = True
    if token_floor is not None:
        ts.token_rights.token_floor_percent = token_floor
        updated = True

    if updated:
        new_term_sheet = ts

    result = client.update_deal(
        deal_id=deal_id,
        status=new_status,
        term_sheet=new_term_sheet,
        approved_by=approved_by,
        revision_note=note,
    )

    if result:
        console.print(f"[green]Updated deal: {deal_id}[/green]")
        console.print(f"Status: {_status_emoji(result.status)} {result.status.value}")
    else:
        console.print("[red]Failed to update deal[/red]")


@app.command("approve")
def approve_deal_cmd(
    deal_id: str = typer.Argument(..., help="Deal ID to approve"),
    approved_by: str = typer.Option(..., "--by", "-b", help="Approver username"),
):
    """Approve a deal and move to approved status."""
    deal = client.get_deal(deal_id)
    if not deal:
        console.print(f"[red]Deal not found: {deal_id}[/red]")
        raise typer.Exit(1)

    if deal.status == DealStatus.APPROVED:
        console.print("[yellow]Deal already approved[/yellow]")
        return

    result = client.approve_deal(deal_id, approved_by)

    if result:
        console.print(f"[green]✅ Deal approved: {deal_id}[/green]")
        console.print(f"Company: {result.company_name}")
        console.print(f"Amount: {_format_money(result.term_sheet.investment_amount)}")
        console.print(f"Requester: {result.requester_user_name} ({result.requester_user_id})")


@app.command("submit")
def submit_for_approval_cmd(
    deal_id: str = typer.Argument(..., help="Deal ID to submit"),
):
    """Submit a deal for approval (changes status to pending_approval)."""
    deal = client.get_deal(deal_id)
    if not deal:
        console.print(f"[red]Deal not found: {deal_id}[/red]")
        raise typer.Exit(1)

    result = client.submit_for_approval(deal_id)

    if result:
        console.print(f"[green]⏳ Deal submitted for approval: {deal_id}[/green]")


@app.command("sent")
def mark_sent_cmd(
    deal_id: str = typer.Argument(..., help="Deal ID to mark as sent"),
):
    """Mark a deal as sent to the company."""
    deal = client.get_deal(deal_id)
    if not deal:
        console.print(f"[red]Deal not found: {deal_id}[/red]")
        raise typer.Exit(1)

    result = client.mark_sent(deal_id)

    if result:
        console.print(f"[green]📤 Deal marked as sent: {deal_id}[/green]")


@app.command("delete")
def delete_term_sheet(
    deal_id: str = typer.Argument(..., help="Deal ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a deal."""
    deal = client.get_deal(deal_id)
    if not deal:
        console.print(f"[red]Deal not found: {deal_id}[/red]")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Delete deal {deal_id} ({deal.company_name})?")
        if not confirm:
            raise typer.Abort()

    if client.delete_deal(deal_id):
        console.print(f"[green]Deleted deal: {deal_id}[/green]")
    else:
        console.print("[red]Failed to delete deal[/red]")


@app.command("email")
def generate_email(
    identifier: str = typer.Argument(..., help="Deal ID or company name"),
    dri: str | None = typer.Option(None, "--dri", help="DRI name override"),
):
    """Generate a draft email for a deal."""
    deal = client.get_deal(identifier)

    if not deal:
        console.print(f"[red]Deal not found: {identifier}[/red]")
        raise typer.Exit(1)

    email = client.generate_email(deal.term_sheet, dri_name=dri)
    console.print(email)


@app.command("thread")
def get_by_thread(
    channel: str = typer.Argument(..., help="Slack channel ID"),
    thread_ts: str = typer.Argument(..., help="Slack thread timestamp"),
):
    """Get deal by Slack thread."""
    deal = client.get_deal_by_thread(channel, thread_ts)

    if not deal:
        console.print("[yellow]No deal found for this thread[/yellow]")
        raise typer.Exit(1)

    console.print(f"[bold]{deal.company_name}[/bold] ({deal.id})")
    console.print(f"Status: {_status_emoji(deal.status)} {deal.status.value}")


if __name__ == "__main__":
    app()
