from datetime import date, datetime, timedelta, timezone

from recon.reconciler.classify import classify_rows
from recon.reconciler.fees import check_fees
from recon.reconciler.integrity import check_payout_integrity
from recon.reconciler.load import load_ledger, load_payout_lines, load_payouts
from recon.reconciler.match import match_rows
from recon.reconciler.models import (
    BankLine,
    BankPayout,
    LedgerRow,
    MatchResult,
    MatchedPair,
    ReasonCode,
)


IST = timezone(timedelta(hours=5, minutes=30))


def ledger(
    ref: str, amount: int, fee: int, created: datetime, kind: str = "payment"
) -> LedgerRow:
    return LedgerRow(ref, kind, "", amount, fee, created)


def bank_line(
    ref: str, amount: int, payout: str = "P1", line_id: str = "B1", kind: str = "PAYMENT"
) -> BankLine:
    return BankLine(payout, line_id, ref, amount, kind)


def payout(payout_id: str, gross: int, fee: int, net: int, day: date | None = None) -> BankPayout:
    return BankPayout(payout_id, day or date(2026, 10, 5), gross, fee, net)


def test_integrity_checks_line_sum_and_net_header() -> None:
    errors = check_payout_integrity(
        [payout("P1", gross=1_000, fee=20, net=980)],
        [bank_line("R1", 900)],
    )
    assert [item.reason_code for item in errors] == [ReasonCode.BANK_INTEGRITY]
    assert errors[0].amount_paise == -100

    errors = check_payout_integrity(
        [payout("P1", gross=1_000, fee=20, net=979)],
        [bank_line("R1", 1_000)],
    )
    assert errors[0].amount_paise == 1


def test_load_normalizes_csv_money_dates_and_ist_timestamp(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.csv"
    ledger_path.write_text(
        "txn_ref,type,original_ref,amount_paise,fee_paise,created_at\n"
        "R1,payment,,12345,247,2026-10-01T12:00:00+05:30\n",
        encoding="utf-8",
    )
    payouts_path = tmp_path / "payouts.csv"
    payouts_path.write_text(
        "payout_id,payout_date,gross,fee,net\nP1,02-10-2026,123.45,2.47,120.98\n",
        encoding="utf-8",
    )
    lines_path = tmp_path / "lines.csv"
    lines_path.write_text(
        "payout_id,bank_line_id,merchant_ref,amount,line_type\nP1,B1,R1,123.45,PAYMENT\n",
        encoding="utf-8",
    )

    assert load_ledger(ledger_path)[0].amount_paise == 12_345
    assert load_ledger(ledger_path)[0].created_at.utcoffset() == timedelta(hours=5, minutes=30)
    assert load_payouts(payouts_path)[0].payout_date == date(2026, 10, 2)
    assert load_payouts(payouts_path)[0].fee_paise == 247
    assert load_payout_lines(lines_path)[0].amount_paise == 12_345


def test_match_uses_earliest_occurrences_and_retains_duplicates() -> None:
    rows = [
        ledger("R1", 1_000, 20, datetime(2026, 10, 2, tzinfo=IST)),
        ledger("R1", 1_000, 20, datetime(2026, 10, 3, tzinfo=IST)),
    ]
    lines = [
        bank_line("R1", 1_000, payout="P2", line_id="B2"),
        bank_line("R1", 1_000, payout="P1", line_id="B1"),
    ]
    result = match_rows(
        rows,
        lines,
        [payout("P1", 2_000, 40, 1_960), payout("P2", 0, 0, 0)],
    )
    assert result.matched[0].ledger == rows[0]
    assert result.matched[0].bank == lines[1]
    assert result.duplicate_ledger == [rows[1]]
    assert result.duplicate_bank == [lines[0]]


def test_match_records_amount_mismatch_and_bank_only_reference() -> None:
    row = ledger("R1", 1_000, 20, datetime(2026, 10, 2, tzinfo=IST))
    lines = [bank_line("R1", 900), bank_line("ORPHAN", -300, line_id="B2", kind="REFUND")]
    result = match_rows([row], lines, [payout("P1", 600, 20, 580)])
    assert result.amount_mismatches == result.matched
    assert result.bank_only == [lines[1]]


def test_classify_period_edges_and_bank_only_refund() -> None:
    rows = [
        ledger("TRANSIT", 1_000, 20, datetime(2026, 10, 31, 12, tzinfo=IST)),
        ledger("OVERDUE", 1_000, 20, datetime(2026, 10, 1, 12, tzinfo=IST)),
        ledger("OUT", 1_000, 20, datetime(2026, 9, 28, 12, tzinfo=IST)),
        ledger("SEP_DUE", 1_000, 20, datetime(2026, 9, 30, 12, tzinfo=IST)),
    ]
    previous = ledger("PREV", 1_000, 20, datetime(2026, 9, 30, 12, tzinfo=IST))
    matched_line = bank_line("PREV", 1_000)
    refund = bank_line("UNKNOWN", -300, line_id="B2", kind="REFUND")
    matches = MatchResult(
        matched=[MatchedPair(previous, matched_line)],
        ledger_only=rows,
        bank_only=[refund],
    )

    result = classify_rows(matches, date(2026, 10, 1), date(2026, 10, 31))
    assert {row.txn_ref: code for row, code in result.ledger} == {
        "TRANSIT": ReasonCode.IN_TRANSIT,
        "OVERDUE": ReasonCode.OVERDUE,
        "OUT": ReasonCode.OUT_OF_WINDOW,
        "SEP_DUE": ReasonCode.OVERDUE,
    }
    assert result.matched[0][1] == ReasonCode.PRIOR_PERIOD_SETTLED
    assert result.bank[0][1] == ReasonCode.ORPHAN_REFUND


def test_fee_tolerance_boundary_and_first_value_beyond_it() -> None:
    row = ledger("R1", 5_000, 100, datetime(2026, 10, 2, tzinfo=IST))
    line = bank_line("R1", 5_000)
    matches = MatchResult(matched=[MatchedPair(row, line)])

    at_boundary = check_fees([payout("P1", 5_000, 99, 4_901)], [line], matches)
    beyond = check_fees([payout("P1", 5_000, 98, 4_902)], [line], matches)
    assert at_boundary[0].reason_code == ReasonCode.FEE_DRIFT
    assert beyond[0].reason_code == ReasonCode.FEE_MISMATCH
