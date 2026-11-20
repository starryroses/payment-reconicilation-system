"""Thin stateless HTTP layer for the committed reconciliation files."""

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from recon import settings
from recon.money import paise_to_rupees
from recon.reconciler.engine import reconcile
from recon.reconciler.models import ReasonCode, Report
from validate import validate_report


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app = FastAPI(title="Payment Reconciliation", version="1.0.0")

INFORMATIONAL_CODES = {
    ReasonCode.IN_TRANSIT,
    ReasonCode.PRIOR_PERIOD_SETTLED,
    ReasonCode.OUT_OF_WINDOW,
    ReasonCode.FEE_DRIFT,
}

BRIDGE_LABELS = {
    "ledger_net_oct": "October ledger net",
    "in_transit": "Less: in transit",
    "prior_period_settled": "Add: prior-period settled",
    "overdue": "Less: overdue",
    "fee_adjustment": "Fee rounding or fee difference",
    "duplicate_bank_credit": "Add: duplicate bank credit",
    "bank_only_payment": "Add: bank-only payment",
    "orphan_refund": "Add: orphan refund",
    "duplicate_ledger": "Less: duplicate ledger rows",
    "amount_mismatch": "Matched amount differences",
    "explained_bank_net": "Explained bank net",
    "bank_net": "Bank net from payout headers",
    "residual": "Residual",
}


def _rupees(amount_paise: int) -> str:
    return format(paise_to_rupees(amount_paise), "f")


def _found_discrepancies(report: Report) -> list[dict[str, Any]]:
    return [
        {
            "type": item.reason_code.value,
            "txn_ref": item.txn_ref,
            "bank_line_id": item.bank_line_id,
            "payout_id": item.payout_id,
            "amount": _rupees(item.amount_paise),
        }
        for item in report.exceptions
        if item.actionable
        and item.reason_code in (ReasonCode.DUPLICATE_BANK, ReasonCode.ORPHAN_REFUND)
    ]


def build_report_payload(data_dir: str | Path = DATA_DIR) -> dict[str, Any]:
    """Read current committed inputs and format a JSON-safe report."""
    directory = Path(data_dir)
    files = {
        "ledger": directory / "ledger.csv",
        "payouts": directory / "payouts.csv",
        "payout_lines": directory / "payout_lines.csv",
    }
    report = reconcile(files)
    with open(directory / "ground_truth.json", encoding="utf-8") as source:
        ground_truth = json.load(source)
    validation_errors = validate_report(report, ground_truth)

    expected_discrepancies = [
        {
            "type": item["type"],
            "txn_ref": item["txn_ref"],
            "bank_line_id": item["bank_line_id"],
            "payout_id": item["payout_id"],
            "amount": _rupees(item["amount_paise"]),
        }
        for item in ground_truth["injected_discrepancies"]
    ]
    found_by_reason = {
        ReasonCode.IN_TRANSIT: {
            item.txn_ref
            for item in report.exceptions
            if item.reason_code == ReasonCode.IN_TRANSIT and item.txn_ref
        },
        ReasonCode.PRIOR_PERIOD_SETTLED: {
            item.txn_ref
            for item in report.exceptions
            if item.reason_code == ReasonCode.PRIOR_PERIOD_SETTLED and item.txn_ref
        },
        ReasonCode.OUT_OF_WINDOW: {
            item.txn_ref
            for item in report.exceptions
            if item.reason_code == ReasonCode.OUT_OF_WINDOW and item.txn_ref
        },
    }
    truth_key_by_reason = {
        ReasonCode.IN_TRANSIT: "in_transit_refs",
        ReasonCode.PRIOR_PERIOD_SETTLED: "prior_period_settled_refs",
        ReasonCode.OUT_OF_WINDOW: "out_of_window_refs",
    }
    cross_month = []
    for reason, truth_key in truth_key_by_reason.items():
        expected_refs = set(ground_truth[truth_key])
        actual_refs = found_by_reason[reason]
        cross_month.append(
            {
                "reason_code": reason.value,
                "expected_count": len(expected_refs),
                "found_count": len(actual_refs),
                "matches": expected_refs == actual_refs,
            }
        )

    exceptions = [
        {
            "reason_code": item.reason_code.value,
            "amount": _rupees(item.amount_paise),
            "txn_ref": item.txn_ref,
            "bank_line_id": item.bank_line_id,
            "payout_id": item.payout_id,
            "explanation": item.explanation,
            "actionable": item.actionable,
            "kind": "informational" if item.reason_code in INFORMATIONAL_CODES else "actionable",
        }
        for item in report.exceptions
    ]
    counts = [
        {"reason_code": code.value, "count": report.counts.get(code, 0)}
        for code in ReasonCode
    ]
    bridge = [
        {"key": key, "label": BRIDGE_LABELS[key], "amount": _rupees(amount)}
        for key, amount in report.bridge_paise.items()
    ]
    return {
        "period": f"{settings.PERIOD_START:%d %b %Y} to {settings.PERIOD_END:%d %b %Y}",
        "verdict": report.verdict.value,
        "headline_totals": [
            {"label": "October ledger net", "amount": _rupees(report.ledger_net_oct_paise)},
            {"label": "Explained bank net", "amount": _rupees(report.explained_bank_net_paise)},
            {"label": "Bank net", "amount": _rupees(report.bank_net_paise)},
            {"label": "Residual", "amount": _rupees(report.residual_paise)},
        ],
        "counts": counts,
        "bridge": bridge,
        "exceptions": exceptions,
        "validation": {
            "passed": not validation_errors,
            "errors": validation_errors,
            "expected_discrepancies": expected_discrepancies,
            "found_discrepancies": _found_discrepancies(report),
            "cross_month": cross_month,
        },
    }


@app.get("/", include_in_schema=False)
def index(request: Request):
    report = build_report_payload()
    return TEMPLATES.TemplateResponse(
        request=request,
        name="index.html",
        context={"report": report},
    )


@app.get("/api/report")
def api_report() -> dict[str, Any]:
    return build_report_payload()
