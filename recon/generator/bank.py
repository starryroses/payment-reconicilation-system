"""Bank-side settlement timing and payout file generation."""

import csv
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from recon import settings
from recon.money import fee_paise, paise_to_rupees
from recon.settings import SETTLEMENT_CUTOFF
from recon.generator.world import Event


def expected_settlement_date(created_at: datetime) -> date:
    """Return the bank's due date, counting only strictly later weekdays."""
    if created_at.tzinfo is None or created_at.utcoffset() != timedelta(hours=5, minutes=30):
        raise ValueError("created_at must be an IST-aware datetime")

    remaining_weekdays = 2 if created_at.time() >= SETTLEMENT_CUTOFF else 1
    due_date = date(created_at.year, created_at.month, created_at.day)

    while remaining_weekdays > 0:
        due_date += timedelta(days=1)
        if due_date.weekday() < 5:
            remaining_weekdays -= 1

    return due_date


def _rupee_text(amount_paise: int) -> str:
    return format(paise_to_rupees(amount_paise), "f")


def write_bank_files(
    events: list[Event], payouts_path: str | Path, payout_lines_path: str | Path
) -> None:
    """Batch bank lines by due date and write October payout headers and details."""
    due_events: dict[date, list[Event]] = defaultdict(list)
    for event in events:
        due_day = expected_settlement_date(event.created_at)
        if settings.PERIOD_START <= due_day <= settings.PERIOD_END:
            due_events[due_day].append(event)

    payout_rows: list[list[str]] = []
    line_rows: list[list[str]] = []
    next_line_number = 1
    for payout_day in sorted(due_events):
        payout_id = f"PAY-{payout_day:%Y%m%d}"
        payout_events = sorted(
            due_events[payout_day], key=lambda event: (event.created_at, event.txn_ref)
        )
        gross_paise = sum(event.amount_paise for event in payout_events)
        positive_base_paise = sum(
            event.amount_paise for event in payout_events if event.amount_paise > 0
        )
        fee = fee_paise(positive_base_paise)
        payout_rows.append(
            [
                payout_id,
                payout_day.strftime("%d-%m-%Y"),
                _rupee_text(gross_paise),
                _rupee_text(fee),
                _rupee_text(gross_paise - fee),
            ]
        )

        for event in payout_events:
            line_rows.append(
                [
                    payout_id,
                    f"BL{next_line_number:09d}",
                    event.txn_ref,
                    _rupee_text(event.amount_paise),
                    "PAYMENT" if event.amount_paise > 0 else "REFUND",
                ]
            )
            next_line_number += 1

    with open(payouts_path, "w", newline="", encoding="utf-8") as destination:
        writer = csv.writer(destination)
        writer.writerow(["payout_id", "payout_date", "gross", "fee", "net"])
        writer.writerows(payout_rows)

    with open(payout_lines_path, "w", newline="", encoding="utf-8") as destination:
        writer = csv.writer(destination)
        writer.writerow(["payout_id", "bank_line_id", "merchant_ref", "amount", "line_type"])
        writer.writerows(line_rows)
