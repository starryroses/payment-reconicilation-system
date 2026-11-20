"""Compare a reconciliation report with the generator's answer key."""

import argparse
import json
from pathlib import Path

from recon.reconciler.engine import reconcile
from recon.reconciler.models import ReasonCode, Report


def validate_report(report: Report, ground_truth: dict[str, object]) -> list[str]:
    """Return validation errors; an empty list means every expected case matched."""
    errors: list[str] = []
    expected_discrepancies = ground_truth["injected_discrepancies"]
    if not isinstance(expected_discrepancies, list):
        raise ValueError("ground truth injected_discrepancies must be a list")

    actionable = [item for item in report.exceptions if item.actionable]
    actual_discrepancies = [
        {
            "type": item.reason_code.value,
            "txn_ref": item.txn_ref,
            "bank_line_id": item.bank_line_id,
            "payout_id": item.payout_id,
            "amount_paise": item.amount_paise,
        }
        for item in actionable
        if item.reason_code in (ReasonCode.DUPLICATE_BANK, ReasonCode.ORPHAN_REFUND)
    ]
    expected_projection = [
        {
            "type": item["type"],
            "txn_ref": item["txn_ref"],
            "bank_line_id": item["bank_line_id"],
            "payout_id": item["payout_id"],
            "amount_paise": item["amount_paise"],
        }
        for item in expected_discrepancies
    ]
    if sorted(actual_discrepancies, key=lambda item: item["type"]) != sorted(
        expected_projection, key=lambda item: item["type"]
    ):
        errors.append("planted discrepancies do not match their expected type, ref, line, payout, and amount")
    if len(actionable) != len(expected_discrepancies):
        errors.append(
            f"expected {len(expected_discrepancies)} actionable items, found {len(actionable)}"
        )

    expected_sets = {
        ReasonCode.IN_TRANSIT: set(ground_truth["in_transit_refs"]),
        ReasonCode.PRIOR_PERIOD_SETTLED: set(ground_truth["prior_period_settled_refs"]),
        ReasonCode.OUT_OF_WINDOW: set(ground_truth["out_of_window_refs"]),
    }
    for reason, expected_refs in expected_sets.items():
        actual_refs = {
            item.txn_ref
            for item in report.exceptions
            if item.reason_code == reason and item.txn_ref is not None
        }
        if actual_refs != expected_refs:
            errors.append(
                f"{reason.value} refs differ: expected {len(expected_refs)}, found {len(actual_refs)}"
            )
    if report.residual_paise != 0:
        errors.append(f"bridge residual is {report.residual_paise} paise")
    return errors


def validate_directory(data_dir: str | Path) -> list[str]:
    """Run reconciliation on a data directory and validate its ground truth."""
    directory = Path(data_dir)
    files = {
        "ledger": directory / "ledger.csv",
        "payouts": directory / "payouts.csv",
        "payout_lines": directory / "payout_lines.csv",
    }
    with open(directory / "ground_truth.json", encoding="utf-8") as source:
        truth = json.load(source)
    report = reconcile(files)
    return validate_report(report, truth)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate reconciliation against the answer key.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    errors = validate_directory(args.data_dir)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    print("Validation passed: planted discrepancies and cross-month sets match.")


if __name__ == "__main__":
    main()
