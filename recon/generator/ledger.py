"""Write the platform ledger view from true-world events."""

import csv
from pathlib import Path

from recon.money import fee_paise
from recon.generator.world import Event


def write_ledger(events: list[Event], path: str | Path) -> None:
    """Write signed event amounts and per-payment transaction fees."""
    with open(path, "w", newline="", encoding="utf-8") as destination:
        writer = csv.writer(destination)
        writer.writerow(
            ["txn_ref", "type", "original_ref", "amount_paise", "fee_paise", "created_at"]
        )
        for event in sorted(events, key=lambda item: (item.created_at, item.txn_ref)):
            fee = fee_paise(event.amount_paise) if event.event_type == "payment" else 0
            writer.writerow(
                [
                    event.txn_ref,
                    event.event_type,
                    event.original_ref,
                    event.amount_paise,
                    fee,
                    event.created_at.isoformat(timespec="seconds"),
                ]
            )
