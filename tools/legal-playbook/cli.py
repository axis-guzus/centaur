"""CLI for legal-playbook checks and defaults."""

from __future__ import annotations

import json

import typer
from dotenv import load_dotenv

from .client import LegalPlaybookClient

load_dotenv()

app = typer.Typer(help="Paradigm legal playbook helper CLI")
client = LegalPlaybookClient()


@app.command("red-lines")
def red_lines() -> None:
    """Print Paradigm red lines."""
    typer.echo(json.dumps(client.get_red_lines(), indent=2))


@app.command("checks")
def checks() -> None:
    """Print the 11 Paradigm verification checks."""
    typer.echo(json.dumps(client.get_paradigm_checks(), indent=2))


@app.command("standards")
def standards(document_type: str = typer.Argument("term_sheet")) -> None:
    """Print default terms for a document type."""
    typer.echo(json.dumps(client.get_standard_terms(document_type), indent=2))


@app.command("compliance")
def compliance(
    document_text: str = typer.Argument(..., help="Document text to evaluate"),
    document_type: str = typer.Option("term_sheet", "--doc-type", help="Document type label"),
) -> None:
    """Run compliance checks against input text."""
    report = client.check_compliance(document_text=document_text, document_type=document_type)
    typer.echo(json.dumps(report, indent=2))


@app.command("clause-defaults")
def clause_defaults() -> None:
    """Print git-committed clause defaults for termsheet generation."""
    typer.echo(json.dumps(client.get_clause_defaults(), indent=2))


if __name__ == "__main__":
    app()
