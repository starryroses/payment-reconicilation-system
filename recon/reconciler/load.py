"""Read the three input CSVs and normalize money and timestamps."""

import csv
from datetime import date, datetime, timedelta
from pathlib import Path

from recon.money import rupees_to_paise
from recon.reconciler.models import BankLine, BankPayout, LedgerRow


def _rows(path: str | Path, required_columns: set[str]) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
            raise ValueError(f"{path} is missing required columns: {sorted(required_columns)}")
        return list(reader)


def load_ledger(path: str | Path) -> list[LedgerRow]:
    required = {"txn_ref", "type", "original_ref", "amount_paise", "fee_paise", "created_at"}
    rows = _rows(path, required)
    loaded: list[LedgerRow] = []
    for row in rows:
        created_at = datetime.fromisoformat(row["created_at"])
        if created_at.utcoffset() != timedelta(hours=5, minutes=30):
            raise ValueError(f"ledger timestamp for {row['txn_ref']} is not IST")
        loaded.append(
            LedgerRow(
                txn_ref=row["txn_ref"],
                type=row["type"],
                original_ref=row["original_ref"],
                amount_paise=int(row["amount_paise"]),
                fee_paise=int(row["fee_paise"]),
                created_at=created_at,
            )
        )
    return loaded


def load_payouts(path: str | Path) -> list[BankPayout]:
    required = {"payout_id", "payout_date", "gross", "fee", "net"}
    rows = _rows(path, required)
    return [
        BankPayout(
            payout_id=row["payout_id"],
            payout_date=datetime.strptime(row["payout_date"], "%d-%m-%Y").date(),
            gross_paise=rupees_to_paise(row["gross"]),
            fee_paise=rupees_to_paise(row["fee"]),
            net_paise=rupees_to_paise(row["net"]),
        )
        for row in rows
    ]


def load_payout_lines(path: str | Path) -> list[BankLine]:
    required = {"payout_id", "bank_line_id", "merchant_ref", "amount", "line_type"}
    rows = _rows(path, required)
    return [
        BankLine(
            payout_id=row["payout_id"],
            bank_line_id=row["bank_line_id"],
            merchant_ref=row["merchant_ref"],
            amount_paise=rupees_to_paise(row["amount"]),
            line_type=row["line_type"],
        )
        for row in rows
    ]
