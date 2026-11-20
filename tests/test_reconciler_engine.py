from datetime import date, datetime, timedelta, timezone

import pytest

import recon.reconciler.engine as engine_module
from recon.reconciler.engine import check_completeness, reconcile
from recon.reconciler.models import ClassificationResult, LedgerRow, ReasonCode, Verdict


IST = timezone(timedelta(hours=5, minutes=30))


def write_fixture_files(tmp_path):
    ledger_path = tmp_path / "ledger.csv"
    ledger_path.write_text(
        "txn_ref,type,original_ref,amount_paise,fee_paise,created_at\n"
        "MATCHED,payment,,10000,200,2026-10-01T12:00:00+05:30\n"
        "TRANSIT,payment,,5000,100,2026-10-30T18:00:00+05:30\n"
        "OVERDUE,payment,,7000,140,2026-10-01T12:00:00+05:30\n"
        "PRIOR,payment,,3000,60,2026-09-30T12:00:00+05:30\n",
        encoding="utf-8",
    )
    payouts_path = tmp_path / "payouts.csv"
    payouts_path.write_text(
        "payout_id,payout_date,gross,fee,net\n"
        "P1,05-10-2026,200.00,4.00,196.00\n"
        "P2,05-10-2026,30.00,0.60,29.40\n"
        "P3,06-10-2026,-5.00,0.00,-5.00\n",
        encoding="utf-8",
    )
    lines_path = tmp_path / "payout_lines.csv"
    lines_path.write_text(
        "payout_id,bank_line_id,merchant_ref,amount,line_type\n"
        "P1,B1,MATCHED,100.00,PAYMENT\n"
        "P1,B2,MATCHED,100.00,PAYMENT\n"
        "P2,B3,PRIOR,30.00,PAYMENT\n"
        "P3,B4,ORPHAN,-5.00,REFUND\n",
        encoding="utf-8",
    )
    return {"ledger": ledger_path, "payouts": payouts_path, "payout_lines": lines_path}


def test_hand_calculated_bridge_fixture(tmp_path) -> None:
    report = reconcile(write_fixture_files(tmp_path))

    assert report.ledger_net_oct_paise == 21_560
    assert report.bridge_paise["in_transit"] == -4_900
    assert report.bridge_paise["overdue"] == -6_860
    assert report.bridge_paise["prior_period_settled"] == 2_940
    assert report.bridge_paise["duplicate_bank_credit"] == 9_800
    assert report.bridge_paise["orphan_refund"] == -500
    assert report.bridge_paise["fee_adjustment"] == 0
    assert report.explained_bank_net_paise == 22_040
    assert report.bank_net_paise == 22_040
    assert report.residual_paise == 0
    assert report.verdict == Verdict.RECONCILED_WITH_EXCEPTIONS
    assert report.counts[ReasonCode.DUPLICATE_BANK] == 1
    assert report.counts[ReasonCode.ORPHAN_REFUND] == 1
    assert report.counts[ReasonCode.OVERDUE] == 1


def test_completeness_check_rejects_a_dropped_ledger_row() -> None:
    row = LedgerRow(
        "R1", "payment", "", 1_000, 20, datetime(2026, 10, 1, tzinfo=IST)
    )
    with pytest.raises(ValueError, match="classified ledger rows"):
        check_completeness([row], [], ClassificationResult())


def test_engine_raises_if_a_stage_drops_an_input_row(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        engine_module,
        "classify_rows",
        lambda matches, period_start, period_end: ClassificationResult(),
    )
    with pytest.raises(ValueError, match="classified ledger rows"):
        engine_module.reconcile(write_fixture_files(tmp_path))


def test_corrupt_payout_net_is_reported_and_leaves_residual(tmp_path) -> None:
    files = write_fixture_files(tmp_path)
    files["payouts"].write_text(
        files["payouts"].read_text(encoding="utf-8").replace(
            "196.00", "195.99", 1
        ),
        encoding="utf-8",
    )

    report = reconcile(files)
    assert report.counts[ReasonCode.BANK_INTEGRITY] == 1
    assert report.residual_paise != 0
    assert report.verdict == Verdict.UNEXPLAINED_DIFFERENCE
