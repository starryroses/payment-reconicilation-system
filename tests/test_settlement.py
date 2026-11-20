from datetime import date, datetime, timedelta, timezone

import pytest

from recon.generator.bank import expected_settlement_date as bank_settlement_date
from recon.reconciler.settlement import expected_settlement_date as recon_settlement_date


IST = timezone(timedelta(hours=5, minutes=30))


@pytest.mark.parametrize(
    ("created_at", "expected"),
    [
        (datetime(2026, 10, 2, 17, 59, 59, tzinfo=IST), date(2026, 10, 5)),
        (datetime(2026, 10, 2, 18, 0, 0, tzinfo=IST), date(2026, 10, 6)),
        (datetime(2026, 10, 3, 12, 0, tzinfo=IST), date(2026, 10, 5)),
        (datetime(2026, 10, 4, 18, 30, tzinfo=IST), date(2026, 10, 6)),
        (datetime(2026, 10, 30, 17, 59, 59, tzinfo=IST), date(2026, 11, 2)),
        (datetime(2026, 10, 30, 18, 0, tzinfo=IST), date(2026, 11, 3)),
    ],
)
def test_settlement_boundaries(created_at: datetime, expected: date) -> None:
    assert bank_settlement_date(created_at) == expected
    assert recon_settlement_date(created_at) == expected


def test_independent_rules_agree_across_thousands_of_timestamps() -> None:
    start = datetime(2026, 1, 1, tzinfo=IST)
    checked = 0
    for day_offset in range(100):
        for hour in range(24):
            for minute in (0, 30, 59):
                moment = start + timedelta(days=day_offset, hours=hour, minutes=minute)
                assert bank_settlement_date(moment) == recon_settlement_date(moment)
                checked += 1
    assert checked == 7_200


@pytest.mark.parametrize("function", [bank_settlement_date, recon_settlement_date])
def test_settlement_rejects_naive_or_non_ist_datetimes(function) -> None:
    with pytest.raises(ValueError, match="IST-aware"):
        function(datetime(2026, 10, 2, 17, 0))
    with pytest.raises(ValueError, match="IST-aware"):
        function(datetime(2026, 10, 2, 17, 0, tzinfo=timezone.utc))
