from datetime import timedelta

from recon import settings
from recon.generator.cli import generate_files
from recon.generator.world import MAX_AMOUNT_PAISE, MIN_AMOUNT_PAISE, generate_world
from recon.reconciler.engine import reconcile
from recon.reconciler.models import ReasonCode
from validate import validate_directory


INFORMATIONAL_CODES = {
    ReasonCode.IN_TRANSIT,
    ReasonCode.PRIOR_PERIOD_SETTLED,
    ReasonCode.OUT_OF_WINDOW,
    ReasonCode.FEE_DRIFT,
}


def test_seeded_world_is_deterministic_and_refunds_are_valid() -> None:
    first = generate_world(12345)
    second = generate_world(12345)
    assert first == second

    payments = [event for event in first if event.event_type == "payment"]
    refunds = [event for event in first if event.event_type == "refund"]
    assert len(payments) == settings.OCTOBER_PAYMENT_COUNT + settings.LATE_SEPTEMBER_PAYMENT_COUNT
    assert len({event.txn_ref for event in first}) == len(first)
    assert all(MIN_AMOUNT_PAISE <= event.amount_paise <= MAX_AMOUNT_PAISE for event in payments)
    assert any(event.amount_paise % 50 == 25 for event in payments)
    payments_by_ref = {event.txn_ref: event for event in payments}

    for event in first:
        assert event.created_at.utcoffset() == timedelta(hours=5, minutes=30)
        assert settings.LEDGER_START <= event.created_at.date() <= settings.PERIOD_END
    for refund in refunds:
        original = payments_by_ref[refund.original_ref]
        assert refund.amount_paise == -original.amount_paise
        assert 1 <= (refund.created_at.date() - original.created_at.date()).days <= 10


def test_generator_writes_reproducible_csv_views(tmp_path) -> None:
    first = generate_files(77, tmp_path / "first")
    second = generate_files(77, tmp_path / "second")
    for name in first:
        assert first[name].read_bytes() == second[name].read_bytes()


def test_uninjected_dataset_has_no_actionable_exceptions(tmp_path) -> None:
    files = generate_files(settings.DEFAULT_SEED, tmp_path)
    report = reconcile(files)

    assert report.residual_paise == 0
    assert all(not item.actionable for item in report.exceptions if item.reason_code in INFORMATIONAL_CODES)
    assert all(item.reason_code in INFORMATIONAL_CODES for item in report.exceptions)
    assert not any(item.actionable for item in report.exceptions)
    assert report.counts.get(ReasonCode.FEE_MISMATCH, 0) == 0
    assert report.counts.get(ReasonCode.BANK_INTEGRITY, 0) == 0
    assert report.counts.get(ReasonCode.AMOUNT_MISMATCH, 0) == 0
    assert report.counts.get(ReasonCode.FEE_DRIFT, 0) > 0


def test_injected_dataset_matches_answer_key_and_has_only_two_actions(tmp_path) -> None:
    files = generate_files(settings.DEFAULT_SEED, tmp_path, inject=True)
    report = reconcile(files)

    assert validate_directory(tmp_path) == []
    actionable = [item for item in report.exceptions if item.actionable]
    assert {item.reason_code for item in actionable} == {
        ReasonCode.DUPLICATE_BANK,
        ReasonCode.ORPHAN_REFUND,
    }
    assert len(actionable) == 2
    assert report.residual_paise == 0
    assert report.counts.get(ReasonCode.BANK_INTEGRITY, 0) == 0


def test_injections_and_answer_key_are_deterministic(tmp_path) -> None:
    first = generate_files(9876, tmp_path / "first", inject=True)
    second = generate_files(9876, tmp_path / "second", inject=True)
    for name in first:
        assert first[name].read_bytes() == second[name].read_bytes()
