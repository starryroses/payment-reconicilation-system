"""Independent implementation of the bank's expected settlement calendar."""

from datetime import date, datetime, time, timedelta

from recon.settings import SETTLEMENT_CUTOFF


def expected_settlement_date(created_at: datetime) -> date:
    """Calculate T+1 or T+2, skipping weekends after the transaction date."""
    if created_at.tzinfo is None or created_at.utcoffset() != timedelta(hours=5, minutes=30):
        raise ValueError("created_at must be an IST-aware datetime")

    local_clock = time(
        created_at.hour,
        created_at.minute,
        created_at.second,
        created_at.microsecond,
    )
    days_to_add = 1
    if local_clock >= SETTLEMENT_CUTOFF:
        days_to_add = 2

    settlement_day = created_at.date()
    while days_to_add:
        settlement_day = settlement_day + timedelta(days=1)
        weekday_number = settlement_day.weekday()
        if weekday_number in (0, 1, 2, 3, 4):
            days_to_add = days_to_add - 1

    return settlement_day
