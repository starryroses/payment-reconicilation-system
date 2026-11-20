"""Join the two views by reference and retain every repeated occurrence."""

from collections import defaultdict

from recon.reconciler.models import (
    BankLine,
    BankPayout,
    LedgerRow,
    MatchResult,
    MatchedPair,
)


def match_rows(
    ledger_rows: list[LedgerRow], bank_lines: list[BankLine], payouts: list[BankPayout]
) -> MatchResult:
    ledger_by_ref: dict[str, list[LedgerRow]] = defaultdict(list)
    bank_by_ref: dict[str, list[BankLine]] = defaultdict(list)
    payout_dates = {payout.payout_id: payout.payout_date for payout in payouts}

    for row in ledger_rows:
        ledger_by_ref[row.txn_ref].append(row)
    for line in bank_lines:
        if line.payout_id not in payout_dates:
            raise ValueError(f"bank line {line.bank_line_id} has no payout header")
        bank_by_ref[line.merchant_ref].append(line)

    result = MatchResult()
    for txn_ref in sorted(set(ledger_by_ref) | set(bank_by_ref)):
        ledger_occurrences = sorted(
            ledger_by_ref[txn_ref], key=lambda row: row.created_at
        )
        bank_occurrences = sorted(
            bank_by_ref[txn_ref],
            key=lambda line: (payout_dates[line.payout_id], line.bank_line_id),
        )

        if ledger_occurrences and bank_occurrences:
            pair = MatchedPair(ledger=ledger_occurrences[0], bank=bank_occurrences[0])
            result.matched.append(pair)
            if pair.ledger.amount_paise != pair.bank.amount_paise:
                result.amount_mismatches.append(pair)
            result.duplicate_ledger.extend(ledger_occurrences[1:])
            result.duplicate_bank.extend(bank_occurrences[1:])
        elif ledger_occurrences:
            result.ledger_only.append(ledger_occurrences[0])
            result.duplicate_ledger.extend(ledger_occurrences[1:])
        else:
            result.bank_only.append(bank_occurrences[0])
            result.duplicate_bank.extend(bank_occurrences[1:])

    result.matched.sort(key=lambda pair: (pair.ledger.created_at, pair.ledger.txn_ref))
    return result
