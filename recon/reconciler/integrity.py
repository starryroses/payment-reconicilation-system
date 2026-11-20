"""Check that each payout header agrees with its own detail lines."""

from collections import defaultdict

from recon.reconciler.models import BankLine, BankPayout, ExceptionItem, ReasonCode


def check_payout_integrity(
    payouts: list[BankPayout], lines: list[BankLine]
) -> list[ExceptionItem]:
    lines_by_payout: dict[str, list[BankLine]] = defaultdict(list)
    for line in lines:
        lines_by_payout[line.payout_id].append(line)

    failures: list[ExceptionItem] = []
    payout_ids = {payout.payout_id for payout in payouts}
    for payout in payouts:
        actual_gross = sum(line.amount_paise for line in lines_by_payout[payout.payout_id])
        if actual_gross != payout.gross_paise:
            failures.append(
                ExceptionItem(
                    reason_code=ReasonCode.BANK_INTEGRITY,
                    amount_paise=actual_gross - payout.gross_paise,
                    payout_id=payout.payout_id,
                    explanation="Payout gross does not equal the sum of its bank lines.",
                )
            )
        net_difference = payout.gross_paise - payout.fee_paise - payout.net_paise
        if net_difference != 0:
            failures.append(
                ExceptionItem(
                    reason_code=ReasonCode.BANK_INTEGRITY,
                    amount_paise=net_difference,
                    payout_id=payout.payout_id,
                    explanation="Payout net does not equal gross minus fee.",
                )
            )

    for payout_id in sorted(set(lines_by_payout) - payout_ids):
        failures.append(
            ExceptionItem(
                reason_code=ReasonCode.BANK_INTEGRITY,
                amount_paise=sum(line.amount_paise for line in lines_by_payout[payout_id]),
                payout_id=payout_id,
                explanation="Bank lines refer to a payout with no header.",
            )
        )
    return failures
