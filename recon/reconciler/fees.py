"""Separate expected per-transaction fees from legitimate batch rounding drift."""

from collections import defaultdict

from recon.money import fee_paise
from recon.reconciler.models import (
    BankLine,
    BankPayout,
    ExceptionItem,
    MatchResult,
    ReasonCode,
)


def check_fees(
    payouts: list[BankPayout], bank_lines: list[BankLine], matches: MatchResult
) -> list[ExceptionItem]:
    expected_by_payout: dict[str, int] = defaultdict(int)
    matched_line_keys: set[tuple[str, str]] = set()

    for pair in matches.matched:
        matched_line_keys.add((pair.bank.payout_id, pair.bank.bank_line_id))
        if pair.ledger.type.lower() == "payment" and pair.bank.amount_paise > 0:
            expected_by_payout[pair.bank.payout_id] += pair.ledger.fee_paise

    for line in bank_lines:
        if (line.payout_id, line.bank_line_id) not in matched_line_keys and line.amount_paise > 0:
            expected_by_payout[line.payout_id] += fee_paise(line.amount_paise)

    positive_counts: dict[str, int] = defaultdict(int)
    for line in bank_lines:
        if line.amount_paise > 0:
            positive_counts[line.payout_id] += 1

    exceptions: list[ExceptionItem] = []
    for payout in payouts:
        delta = expected_by_payout[payout.payout_id] - payout.fee_paise
        if delta == 0:
            continue
        within_rounding_bound = 2 * abs(delta) <= positive_counts[payout.payout_id] + 1
        code = ReasonCode.FEE_DRIFT if within_rounding_bound else ReasonCode.FEE_MISMATCH
        exceptions.append(
            ExceptionItem(
                reason_code=code,
                amount_paise=delta,
                payout_id=payout.payout_id,
                explanation=(
                    "Per-transaction and per-payout fee rounding differ."
                    if code == ReasonCode.FEE_DRIFT
                    else "Payout fee differs from the expected fee beyond the rounding bound."
                ),
                actionable=code == ReasonCode.FEE_MISMATCH,
            )
        )
    return exceptions
