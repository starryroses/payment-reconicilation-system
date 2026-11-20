"""Plant the two agreed bank discrepancies and write their answer key."""

import csv
import json
import random
import re
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from recon import settings
from recon.generator.bank import expected_settlement_date
from recon.generator.world import Event
from recon.money import fee_paise, paise_to_rupees, rupees_to_paise


def _money_text(amount_paise: int) -> str:
    return format(paise_to_rupees(amount_paise), "f")


def _next_id(prefix: str, existing: set[str]) -> str:
    largest = 0
    for value in existing:
        match = re.search(r"(\d+)$", value)
        if match:
            largest = max(largest, int(match.group(1)))
    candidate_number = largest + 1
    candidate = f"{prefix}{candidate_number:09d}"
    while candidate in existing:
        candidate_number += 1
        candidate = f"{prefix}{candidate_number:09d}"
    return candidate


def _cross_month_sets(events: list[Event]) -> dict[str, list[str]]:
    transit: list[str] = []
    prior_period: list[str] = []
    out_of_window: list[str] = []
    for event in events:
        transaction_day = event.created_at.date()
        settlement_day = expected_settlement_date(event.created_at)
        if settings.PERIOD_START <= transaction_day <= settings.PERIOD_END:
            if settlement_day > settings.PERIOD_END:
                transit.append(event.txn_ref)
        elif settings.LEDGER_START <= transaction_day < settings.PERIOD_START:
            if settlement_day < settings.PERIOD_START:
                out_of_window.append(event.txn_ref)
            else:
                prior_period.append(event.txn_ref)
    return {
        "in_transit_refs": sorted(transit),
        "prior_period_settled_refs": sorted(prior_period),
        "out_of_window_refs": sorted(out_of_window),
    }


def inject_discrepancies(
    events: list[Event],
    ledger_path: str | Path,
    payouts_path: str | Path,
    payout_lines_path: str | Path,
    ground_truth_path: str | Path,
    seed: int,
) -> dict[str, object]:
    """Add one duplicate payment and one orphan refund in separate payouts."""
    rng = random.Random(seed ^ 0x5E771E)
    with open(ledger_path, newline="", encoding="utf-8") as source:
        ledger_refs = {row["txn_ref"] for row in csv.DictReader(source)}
    with open(payouts_path, newline="", encoding="utf-8") as source:
        payout_rows = list(csv.DictReader(source))
    with open(payout_lines_path, newline="", encoding="utf-8") as source:
        line_rows = list(csv.DictReader(source))

    payment_counts: dict[str, int] = defaultdict(int)
    for row in line_rows:
        if row["line_type"] == "PAYMENT" and rupees_to_paise(row["amount"]) > 0:
            payment_counts[row["payout_id"]] += 1
    duplicate_candidates = [
        row
        for row in line_rows
        if row["line_type"] == "PAYMENT"
        and rupees_to_paise(row["amount"]) > 0
        and payment_counts[row["payout_id"]] >= 2
    ]
    if not duplicate_candidates:
        raise ValueError("cannot inject duplicate: no payout has at least two payment lines")
    duplicate_source = rng.choice(sorted(duplicate_candidates, key=lambda row: row["bank_line_id"]))
    duplicate_payout_id = duplicate_source["payout_id"]
    duplicate_line_id = _next_id("BL", {row["bank_line_id"] for row in line_rows})
    duplicate_copy = dict(duplicate_source)
    duplicate_copy["bank_line_id"] = duplicate_line_id
    line_rows.append(duplicate_copy)

    orphan_candidates = [
        row
        for row in line_rows
        if row["line_type"] == "PAYMENT"
        and rupees_to_paise(row["amount"]) > 0
        and row["payout_id"] != duplicate_payout_id
    ]
    if not orphan_candidates:
        raise ValueError("cannot inject orphan refund: no separate payout has a payment line")
    orphan_source = rng.choice(sorted(orphan_candidates, key=lambda row: row["bank_line_id"]))
    orphan_payout_id = orphan_source["payout_id"]
    orphan_line_id = _next_id(
        "BL", {row["bank_line_id"] for row in line_rows}
    )
    orphan_ref = _next_id("TXN", ledger_refs)
    orphan_amount_paise = -rupees_to_paise(orphan_source["amount"])
    line_rows.append(
        {
            "payout_id": orphan_payout_id,
            "bank_line_id": orphan_line_id,
            "merchant_ref": orphan_ref,
            "amount": _money_text(orphan_amount_paise),
            "line_type": "REFUND",
        }
    )

    lines_by_payout: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in line_rows:
        lines_by_payout[row["payout_id"]].append(row)
    for payout in payout_rows:
        if payout["payout_id"] not in (duplicate_payout_id, orphan_payout_id):
            continue
        payout_lines = lines_by_payout[payout["payout_id"]]
        gross = sum(rupees_to_paise(line["amount"]) for line in payout_lines)
        positive_base = sum(
            rupees_to_paise(line["amount"])
            for line in payout_lines
            if rupees_to_paise(line["amount"]) > 0
        )
        fee = fee_paise(positive_base)
        payout["gross"] = _money_text(gross)
        payout["fee"] = _money_text(fee)
        payout["net"] = _money_text(gross - fee)

    with open(payouts_path, "w", newline="", encoding="utf-8") as destination:
        fields = ["payout_id", "payout_date", "gross", "fee", "net"]
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(payout_rows)
    with open(payout_lines_path, "w", newline="", encoding="utf-8") as destination:
        fields = ["payout_id", "bank_line_id", "merchant_ref", "amount", "line_type"]
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(line_rows)

    truth: dict[str, object] = {
        "seed": seed,
        "injected_discrepancies": [
            {
                "type": "DUPLICATE_BANK",
                "txn_ref": duplicate_source["merchant_ref"],
                "original_bank_line_id": duplicate_source["bank_line_id"],
                "bank_line_id": duplicate_line_id,
                "payout_id": duplicate_payout_id,
                "amount_paise": rupees_to_paise(duplicate_source["amount"]),
            },
            {
                "type": "ORPHAN_REFUND",
                "txn_ref": orphan_ref,
                "bank_line_id": orphan_line_id,
                "payout_id": orphan_payout_id,
                "amount_paise": orphan_amount_paise,
            },
        ],
        **_cross_month_sets(events),
    }
    with open(ground_truth_path, "w", encoding="utf-8") as destination:
        json.dump(truth, destination, indent=2)
        destination.write("\n")
    return truth
