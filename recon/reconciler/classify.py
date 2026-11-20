"""Assign every matched or unmatched occurrence to its reconciliation bucket."""

from datetime import date

from recon.reconciler.models import (
    ClassificationResult,
    MatchResult,
    ReasonCode,
)
from recon.reconciler.settlement import expected_settlement_date


def classify_rows(
    matches: MatchResult, period_start: date, period_end: date
) -> ClassificationResult:
    result = ClassificationResult()

    for pair in matches.matched:
        reason = (
            ReasonCode.PRIOR_PERIOD_SETTLED
            if pair.ledger.created_at.date() < period_start
            else ReasonCode.MATCHED
        )
        result.matched.append((pair, reason))

    for row in matches.ledger_only:
        transaction_day = row.created_at.date()
        due_day = expected_settlement_date(row.created_at)
        if period_start <= transaction_day <= period_end:
            reason = ReasonCode.IN_TRANSIT if due_day > period_end else ReasonCode.OVERDUE
        elif transaction_day < period_start:
            reason = ReasonCode.OUT_OF_WINDOW if due_day < period_start else ReasonCode.OVERDUE
        else:
            raise ValueError(f"ledger row {row.txn_ref} is outside the ledger window")
        result.ledger.append((row, reason))

    for row in matches.duplicate_ledger:
        result.ledger.append((row, ReasonCode.DUPLICATE_LEDGER))

    for line in matches.bank_only:
        reason = ReasonCode.ORPHAN_REFUND if line.amount_paise < 0 else ReasonCode.BANK_ONLY_PAYMENT
        result.bank.append((line, reason))

    for line in matches.duplicate_bank:
        result.bank.append((line, ReasonCode.DUPLICATE_BANK))

    return result
