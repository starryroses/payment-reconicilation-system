"""Pure orchestration for the reconciliation stages."""

from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Mapping

from recon import settings as default_settings
from recon.reconciler.bridge import build_bridge
from recon.reconciler.classify import classify_rows
from recon.reconciler.fees import check_fees
from recon.reconciler.integrity import check_payout_integrity
from recon.reconciler.load import load_ledger, load_payout_lines, load_payouts
from recon.reconciler.match import match_rows
from recon.reconciler.models import (
    BankLine,
    BankPayout,
    ClassificationResult,
    ExceptionItem,
    LedgerRow,
    ReasonCode,
    Report,
    Verdict,
)


def check_completeness(
    ledger_rows: list[LedgerRow],
    bank_lines: list[BankLine],
    classified: ClassificationResult,
) -> None:
    """Raise if any input occurrence is absent or duplicated in classification."""
    classified_ledger = [row for row, _ in classified.ledger]
    classified_ledger.extend(pair.ledger for pair, _ in classified.matched)
    classified_bank = [line for line, _ in classified.bank]
    classified_bank.extend(pair.bank for pair, _ in classified.matched)

    if Counter(map(id, classified_ledger)) != Counter(map(id, ledger_rows)):
        raise ValueError("completeness failure: classified ledger rows do not match input rows")
    if Counter(map(id, classified_bank)) != Counter(map(id, bank_lines)):
        raise ValueError("completeness failure: classified bank lines do not match input lines")
    if sum(row.amount_paise for row in classified_ledger) != sum(
        row.amount_paise for row in ledger_rows
    ):
        raise ValueError("completeness failure: classified ledger amount total changed")
    if sum(line.amount_paise for line in classified_bank) != sum(
        line.amount_paise for line in bank_lines
    ):
        raise ValueError("completeness failure: classified bank amount total changed")


def _exception_items(
    classified: ClassificationResult,
    fee_items: list[ExceptionItem],
    integrity_items: list[ExceptionItem],
) -> list[ExceptionItem]:
    explanations = {
        ReasonCode.IN_TRANSIT: "Ledger transaction settles after the October payout window.",
        ReasonCode.OVERDUE: "Ledger transaction was due in the October payout window but is absent.",
        ReasonCode.OUT_OF_WINDOW: "Ledger transaction was due before the October payout window.",
        ReasonCode.DUPLICATE_LEDGER: "A later ledger row repeats a transaction reference.",
        ReasonCode.PRIOR_PERIOD_SETTLED: "A September ledger transaction settled in October.",
        ReasonCode.DUPLICATE_BANK: "A later bank line repeats a transaction reference.",
        ReasonCode.BANK_ONLY_PAYMENT: "Positive bank line has no ledger transaction reference.",
        ReasonCode.ORPHAN_REFUND: "Negative bank line has no matching ledger refund.",
    }
    informational = {
        ReasonCode.IN_TRANSIT,
        ReasonCode.PRIOR_PERIOD_SETTLED,
        ReasonCode.OUT_OF_WINDOW,
        ReasonCode.FEE_DRIFT,
    }
    items: list[ExceptionItem] = []
    for row, code in classified.ledger:
        items.append(
            ExceptionItem(
                reason_code=code,
                amount_paise=row.amount_paise,
                txn_ref=row.txn_ref,
                explanation=explanations[code],
                actionable=code not in informational,
            )
        )
    for line, code in classified.bank:
        items.append(
            ExceptionItem(
                reason_code=code,
                amount_paise=line.amount_paise,
                txn_ref=line.merchant_ref,
                bank_line_id=line.bank_line_id,
                payout_id=line.payout_id,
                explanation=explanations[code],
                actionable=code not in informational,
            )
        )
    for pair, code in classified.matched:
        if code == ReasonCode.PRIOR_PERIOD_SETTLED:
            items.append(
                ExceptionItem(
                    reason_code=code,
                    amount_paise=pair.bank.amount_paise,
                    txn_ref=pair.ledger.txn_ref,
                    bank_line_id=pair.bank.bank_line_id,
                    payout_id=pair.bank.payout_id,
                    explanation=explanations[code],
                    actionable=False,
                )
            )
        if pair.ledger.amount_paise != pair.bank.amount_paise:
            items.append(
                ExceptionItem(
                    reason_code=ReasonCode.AMOUNT_MISMATCH,
                    amount_paise=pair.bank.amount_paise - pair.ledger.amount_paise,
                    txn_ref=pair.ledger.txn_ref,
                    bank_line_id=pair.bank.bank_line_id,
                    payout_id=pair.bank.payout_id,
                    explanation="Matched transaction reference has different ledger and bank amounts.",
                )
            )
    items.extend(fee_items)
    items.extend(integrity_items)
    return items


def reconcile(
    files: Mapping[str, str | Path], settings: ModuleType = default_settings
) -> Report:
    """Reconcile CSV inputs without mutating the files or shared settings."""
    ledger_rows = load_ledger(files["ledger"])
    payouts = load_payouts(files["payouts"])
    bank_lines = load_payout_lines(files["payout_lines"])

    integrity_items = check_payout_integrity(payouts, bank_lines)
    matches = match_rows(ledger_rows, bank_lines, payouts)
    classified = classify_rows(matches, settings.PERIOD_START, settings.PERIOD_END)
    check_completeness(ledger_rows, bank_lines, classified)
    fee_items = check_fees(payouts, bank_lines, matches)
    bridge = build_bridge(
        ledger_rows,
        payouts,
        classified,
        fee_items,
        settings.PERIOD_START,
        settings.PERIOD_END,
    )
    exceptions = _exception_items(classified, fee_items, integrity_items)
    counts = dict(Counter(item.reason_code for item in exceptions))

    actionable_exists = any(item.actionable for item in exceptions)
    if bridge["residual"] != 0:
        verdict = Verdict.UNEXPLAINED_DIFFERENCE
    elif actionable_exists:
        verdict = Verdict.RECONCILED_WITH_EXCEPTIONS
    else:
        verdict = Verdict.RECONCILED

    return Report(
        verdict=verdict,
        ledger_net_oct_paise=bridge["ledger_net_oct"],
        bank_net_paise=bridge["bank_net"],
        explained_bank_net_paise=bridge["explained_bank_net"],
        residual_paise=bridge["residual"],
        bridge_paise=bridge,
        exceptions=exceptions,
        counts=counts,
    )
