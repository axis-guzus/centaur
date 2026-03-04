"""Plain-text term sheet and draft email generation."""

from .docx_pipeline import format_money, format_money_full
from .models import BoardRights, InstrumentType, TermSheet


def _title(ts: TermSheet) -> str:
    company = ts.company_name.upper()
    series = ts.effective_series.upper()
    if ts.instrument_type == InstrumentType.SAFE:
        return f"{company} SAFE FINANCING\nSUMMARY OF PROPOSED TERMS"
    if ts.instrument_type == InstrumentType.CONVERTIBLE_NOTE:
        return f"{company} CONVERTIBLE NOTE FINANCING\nSUMMARY OF PROPOSED TERMS"
    return f"{company} SERIES {series} PREFERRED STOCK FINANCING\nSUMMARY OF PROPOSED TERMS"


def _investment(ts: TermSheet) -> str:
    amt = format_money(ts.investment_amount)

    if ts.instrument_type == InstrumentType.SAFE:
        parts = [f'Paradigm Fund LP (together with its affiliates, "Paradigm") to invest {amt}']
        if ts.valuation_cap:
            parts.append(f"via a SAFE with a {format_money(ts.valuation_cap)} valuation cap")
        if ts.discount_percent:
            parts.append(f"and {ts.discount_percent:g}% discount")
        parts.append(f'in {ts.company_name} (the "Company").')
        return " ".join(parts)

    if ts.instrument_type == InstrumentType.CONVERTIBLE_NOTE:
        parts = [f'Paradigm Fund LP (together with its affiliates, "Paradigm") to invest {amt}']
        if ts.valuation_cap:
            parts.append(
                f"via convertible note with a {format_money(ts.valuation_cap)} valuation cap"
            )
        if ts.discount_percent:
            parts.append(f"and {ts.discount_percent:g}% discount")
        parts.append(f'in {ts.company_name} (the "Company").')
        return " ".join(parts)

    val = ts.effective_valuation
    ownership = ts.ownership_percent
    val_type = "post-money" if ts.post_money_valuation else "pre-money"
    pool = ts.option_pool_percent

    text = (
        f'Paradigm Fund LP (together with its affiliates, "Paradigm") to invest '
        f"{amt} at a {format_money(val)} {val_type} valuation (including "
        f"conversion of all convertible securities and an unallocated option pool, "
        f"exclusive of granted or promised shares, equal to {pool:g}% of the "
        f"post-money fully diluted capitalization), such that post-closing Paradigm "
        f"will own {ownership:.1f}% of the fully diluted capitalization of "
        f'{ts.company_name} (the "Company").'
    )

    if ts.co_investor_language:
        text += " " + (
            ts.co_investor_text
            or "Other investors mutually acceptable to Paradigm and the Company "
            "may invest additional amounts, which shall not affect the "
            "post-money valuation."
        )

    return text


def _securities(ts: TermSheet) -> str:
    series = ts.effective_series
    ipo = format_money(ts.ipo_threshold)

    if ts.is_seed:
        series_clause = f'Series {series} Preferred Stock (the "Preferred Stock")'
    else:
        series_clause = (
            f"Series {series} Preferred Stock (together with other series of "
            f'Preferred Stock, the "Preferred Stock")'
        )

    return (
        f"{series_clause} with standard non-cumulative dividends in preference "
        f"of Common Stock, {ts.liquidation_preference} liquidation preference "
        f"and {ts.anti_dilution} antidilution protection (subject to limited "
        f"exclusions), that is convertible to Common Stock upon the earlier of "
        f"(i) the election of Preferred Majority (as defined below) or (ii) the "
        f"consummation of an underwritten public offering with net proceeds "
        f"greater than {ipo}."
    )


def _board(ts: TermSheet) -> str:
    series = ts.effective_series
    parts: list[str] = []

    if ts.board_rights in {BoardRights.SEAT, BoardRights.SEAT_AND_OBSERVER}:
        parts.append(
            f"One director to be elected by the Series {series} Preferred Stock "
            f"and designated by Paradigm."
        )

    if ts.board_rights in {BoardRights.OBSERVER, BoardRights.SEAT_AND_OBSERVER}:
        prefix = "In addition, " if ts.board_rights == BoardRights.SEAT_AND_OBSERVER else ""
        conditional = (
            ", if Paradigm has not designated its director,"
            if ts.board_rights == BoardRights.SEAT_AND_OBSERVER
            else ""
        )
        parts.append(
            f"{prefix}Company shall invite a representative of Paradigm to "
            f"attend all meetings of the Board in a nonvoting observer capacity "
            f"and{conditional} the Company shall provide such representative "
            f"copies of all notices, minutes, consents, and other materials "
            f"provided to its directors."
        )

    parts.append(
        "Preferred Stock voting thresholds to be set such that Paradigm's "
        'consent is required (the "Preferred Majority").'
    )
    return " ".join(parts)


def _protective_provisions(ts: TermSheet) -> str:
    debt = format_money(ts.debt_threshold)
    clause_v = ts.protective_provision_v_text or (
        "any interested or related party transactions other than transactions "
        "entered into in the ordinary course of business on an arms-length basis "
        "and benefits made available to all employees"
    )
    return (
        "Consent of the Preferred Majority required for standard NVCA protective "
        "provisions and certain additional protective provisions, including: "
        f"(i) incurrence of indebtedness or issuance of debt securities greater "
        f"than {debt}; "
        "(ii) creation of any new equity compensation plan or increase the number "
        "of shares available for issuance pursuant to such plans; "
        "(iii) any sale, assignment, license, pledge or encumbrance of material "
        "technology or intellectual property of the Company, "
        "(iv) the creation, reservation, sale, distribution, issuance or other "
        'disposition of any tokens ("Tokens") and '
        f"(v) {clause_v.rstrip('.')}."
    )


def _other_rights(ts: TermSheet) -> str:
    if ts.other_rights_text:
        return ts.other_rights_text
    carveout = f"{ts.founder_carveout_percent:g}"
    investor_rights = (
        "Customary NVCA investor rights, including information rights and pro rata "
        "rights (including overallotment) for Major Investors (which shall only "
        "include Paradigm), registration rights for all Investors, drag along "
        "provision, and all 1% Common stockholder's (including founder(s)) equity "
        "and Tokens will be subject to ROFR and co-sale rights (in each case, with "
        "exclusions for transfers to affiliates and for estate planning or the "
        f"aggregate sale or transfer of up to {carveout}% of the stock initially "
        "subject to these provisions)."
    )
    if not ts.pro_rata_rights:
        investor_rights = (
            "Customary NVCA investor rights, including information rights, "
            "registration rights for all Investors, drag along provision, and all "
            "1% Common stockholder's (including founder(s)) equity and Tokens will "
            "be subject to ROFR and co-sale rights (in each case, with exclusions "
            "for transfers to affiliates and for estate planning or the aggregate "
            f"sale or transfer of up to {carveout}% of the stock initially subject "
            "to these provisions)."
        )
    parts = [
        investor_rights,
        "Bylaws to provide for transfer restrictions "
        "on Common Stock, other than transfers to affiliates. Paradigm's shares "
        "shall not be subject to any transfer restrictions. Customary closing "
        "conditions, including a customary legal opinion including with respect to "
        "Company's capitalization, valid issuance of Preferred Stock and "
        "enforceability.",
    ]
    return " ".join(parts)


def _token_rights(ts: TermSheet) -> str:
    if ts.token_rights_text:
        return ts.token_rights_text
    floor = f"{ts.token_rights.token_floor_percent:g}"
    return (
        "For any Tokens (other than non-fungible tokens or other similar assets "
        "developed in the ordinary course of business) useable or accessible in or "
        "through a blockchain-based game or application created by the Company, "
        "founder or affiliates, Paradigm will receive its pro rata share (on a "
        'fully-diluted basis, as of network launch) of the total number of Tokens (the "Launch '
        "Supply\") allocated to or reserved for the Company, the Company's officers, "
        "directors, employees, consultants, stockholders and any convertible "
        'instrument holders (collectively, the "Insiders"). The Launch Supply shall '
        f"be at least {floor}% of the total number of Tokens issuable for such "
        "network. If an inflationary event (the creation of additional Tokens "
        "following network launch) occurs, Paradigm will receive its pro rata share "
        "(on a fully-diluted basis, as of the date of such inflationary event) of "
        "the total number of inflationary tokens allocated to or reserved for "
        "Insiders in connection with such inflationary event. Subject to customary "
        "exceptions, the Company and the founders shall agree that they will not "
        "utilize or exploit protocols related to the Company's business for "
        "commercial purposes other than directly through the Company. Any lockup "
        "schedule on such Tokens shall be no more restrictive than the schedule "
        "applicable to Tokens issued to the Company or Insiders."
    )


def _vesting() -> str:
    return (
        "Founder vesting subject to due diligence. Standard 4-year monthly "
        "vesting with one year cliff for all employees, beginning on first day "
        "of employment."
    )


def _vesting_for(ts: TermSheet) -> str:
    return ts.vesting_text or _vesting()


def _documentation(ts: TermSheet) -> str:
    fee = format_money_full(ts.legal_fee_cap)
    return (
        f"Company counsel to draft documentation based on {ts.nvca_year} NVCA "
        f"forms. Company will pay the reasonable legal fees incurred by "
        f"Paradigm's counsel up to {fee}."
    )


def _no_shop(ts: TermSheet) -> str:
    return (
        f"The Company and the founders agree that they will not, for a period of "
        f"{ts.exclusivity_days} days from the date these terms are accepted, take "
        f"any action to solicit, initiate, encourage or assist the submission of "
        f"any proposal, negotiation or offer from any person or entity other than "
        f"Paradigm relating to the sale or issuance of any of the capital stock of "
        f"the Company. The Company will not disclose the terms of this Term Sheet "
        f"to any person other than officers, members of the Board and the Company's "
        f"accountants and attorneys and other potential investors acceptable to "
        f"Paradigm, without the written consent of Paradigm."
    )


def _disclaimer() -> str:
    return (
        "Except for the No-Shop; Confidentiality provision set forth above, this "
        "term sheet is non-binding and is intended solely to be a summary of the "
        "terms that are currently proposed by the parties. Please indicate your "
        "acceptance of this term sheet by signing below and returning an executed "
        "copy."
    )


def generate_term_sheet_text(ts: TermSheet) -> str:
    """Generate a plain-text term sheet matching Paradigm's document language."""
    sections: list[str] = [_title(ts)]

    sections.append(f"Investment & Post-Money Valuation:\n{_investment(ts)}")

    if ts.instrument_type == InstrumentType.PRICED:
        sections.append(f"Securities:\n{_securities(ts)}")

    sections.append(f"Board and Voting Rights:\n{_board(ts)}")
    sections.append(f"Protective Provisions:\n{_protective_provisions(ts)}")
    sections.append(f"Other Rights:\n{_other_rights(ts)}")

    if ts.token_rights.enabled:
        sections.append(f"Token Rights:\n{_token_rights(ts)}")

    sections.append(f"Vesting:\n{_vesting_for(ts)}")
    sections.append(f"Documentation; Legal Fees:\n{_documentation(ts)}")
    sections.append(f"No-Shop; Confidentiality:\n{_no_shop(ts)}")

    if ts.custom_terms:
        sections.append(f"Additional Terms:\n{ts.custom_terms}")

    sections.append(_disclaimer())

    return "\n\n".join(sections)


def generate_draft_email(ts: TermSheet, dri_name: str = "") -> str:
    """Generate a draft email to accompany a term sheet."""
    recipient = dri_name or "the team"
    amt = format_money(ts.investment_amount)
    val = format_money(ts.effective_valuation) if ts.effective_valuation else ""

    subject = f"Paradigm — {ts.company_name} Term Sheet"

    val_clause = f" at a {val} post-money valuation" if val else ""
    body = (
        f"Subject: {subject}\n\n"
        f"Hi {recipient},\n\n"
        f"Attached is a term sheet reflecting Paradigm's proposal to invest "
        f"{amt}{val_clause} in {ts.company_name}.\n\n"
        f"We are excited about the opportunity and look forward to working "
        f"together. Please review and let us know if you have any questions.\n\n"
        f"Best,\nBen"
    )
    return body
