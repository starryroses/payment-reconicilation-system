"""Build the October cash bridge from ledger and classified bank movements."""

from datetime import date

from recon.money import fee_paise
from recon.reconciler.models import (
    BankPayout,
    ClassificationResult,
    ExceptionItem,
    LedgerRow,
    ReasonCode,
)


def build_bridge(
    ledger_rows: list[LedgerRow],
    payouts: list[BankPayout],
    classified: ClassificationResult,
    fee_items: list[ExceptionItem],
    period_start: date,
    period_end: date,
) -> dict[str, int]:
    """Return signed paise adjustments from October ledger net to bank net."""
    ledger_net = sum(
        row.amount_paise - row.fee_paise
        for row in ledger_rows
        if period_start <= row.created_at.date() <= period_end
    )
    bank_net = sum(
        payout.net_paise for payout in payouts if period_start <= payout.payout_date <= period_end
    )

    adjustments = {
        "in_transit": 0,
        "prior_period_settled": 0,
        "overdue": 0,
        "fee_adjustment": sum(item.amount_paise for item in fee_items),
        "duplicate_bank_credit": 0,
        "bank_only_payment": 0,
        "orphan_refund": 0,
        "duplicate_ledger": 0,
        "amount_mismatch": 0,
    }

    for row, reason in classified.ledger:
        ledger_net_amount = row.amount_paise - row.fee_paise
        if reason == ReasonCode.IN_TRANSIT:
            adjustments["in_transit"] -= ledger_net_amount
        elif reason == ReasonCode.OVERDUE:
            adjustments["overdue"] -= ledger_net_amount
        elif reason == ReasonCode.DUPLICATE_LEDGER and period_start <= row.created_at.date() <= period_end:
            adjustments["duplicate_ledger"] -= ledger_net_amount

    for pair, reason in classified.matched:
        if reason == ReasonCode.PRIOR_PERIOD_SETTLED:
            per_transaction_fee = pair.ledger.fee_paise if pair.bank.amount_paise > 0 else 0
            adjustments["prior_period_settled"] += pair.bank.amount_paise - per_transaction_fee
        if pair.ledger.amount_paise != pair.bank.amount_paise:
            adjustments["amount_mismatch"] += pair.bank.amount_paise - pair.ledger.amount_paise

    for line, reason in classified.bank:
        if reason in (ReasonCode.DUPLICATE_BANK, ReasonCode.BANK_ONLY_PAYMENT):
            line_fee = fee_paise(line.amount_paise) if line.amount_paise > 0 else 0
            adjustment = line.amount_paise - line_fee
            if reason == ReasonCode.DUPLICATE_BANK:
                adjustments["duplicate_bank_credit"] += adjustment
            else:
                adjustments["bank_only_payment"] += adjustment
        elif reason == ReasonCode.ORPHAN_REFUND:
            adjustments["orphan_refund"] += line.amount_paise

    explained = ledger_net + sum(adjustments.values())
    return {
        "ledger_net_oct": ledger_net,
        **adjustments,
        "explained_bank_net": explained,
        "bank_net": bank_net,
        "residual": bank_net - explained,
    }
