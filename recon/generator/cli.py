"""Seeded command-line entry point for generating the three source files."""

import argparse
from pathlib import Path

from recon import settings
from recon.generator.bank import write_bank_files
from recon.generator.inject import inject_discrepancies
from recon.generator.ledger import write_ledger
from recon.generator.world import generate_world


def generate_files(
    seed: int, output_dir: str | Path, inject: bool = False
) -> dict[str, Path]:
    """Generate deterministic files, optionally adding the agreed test cases."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    events = generate_world(seed)

    ledger_path = destination / "ledger.csv"
    payouts_path = destination / "payouts.csv"
    payout_lines_path = destination / "payout_lines.csv"
    write_ledger(events, ledger_path)
    write_bank_files(events, payouts_path, payout_lines_path)
    files = {
        "ledger": ledger_path,
        "payouts": payouts_path,
        "payout_lines": payout_lines_path,
    }
    if inject:
        truth_path = destination / "ground_truth.json"
        inject_discrepancies(
            events,
            ledger_path,
            payouts_path,
            payout_lines_path,
            truth_path,
            seed,
        )
        files["ground_truth"] = truth_path
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate seeded reconciliation input files.")
    parser.add_argument("--seed", type=int, default=settings.DEFAULT_SEED)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--inject",
        action="store_true",
        help="plant one duplicate bank payment and one orphan refund",
    )
    args = parser.parse_args()

    files = generate_files(args.seed, args.output_dir, inject=args.inject)
    print(f"Generated seed {args.seed}:")
    for name, path in files.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
