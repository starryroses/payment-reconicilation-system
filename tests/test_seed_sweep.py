import pytest

from recon.generator.cli import generate_files
from recon.reconciler.engine import reconcile
from recon.reconciler.models import ReasonCode
from validate import validate_directory


@pytest.mark.parametrize("seed", range(202600, 202650))
def test_generated_and_injected_dataset_across_seeds(seed: int, tmp_path) -> None:
    files = generate_files(seed, tmp_path, inject=True)
    report = reconcile(files)

    assert validate_directory(tmp_path) == []
    assert report.residual_paise == 0
    assert report.counts.get(ReasonCode.BANK_INTEGRITY, 0) == 0
    assert report.counts.get(ReasonCode.FEE_MISMATCH, 0) == 0
    assert {item.reason_code for item in report.exceptions if item.actionable} == {
        ReasonCode.DUPLICATE_BANK,
        ReasonCode.ORPHAN_REFUND,
    }
