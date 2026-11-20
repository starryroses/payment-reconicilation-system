"""Create seeded true-world payment and refund events."""

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from recon import settings


IST = timezone(timedelta(hours=5, minutes=30))
MIN_AMOUNT_PAISE = 10_000
MAX_AMOUNT_PAISE = 5_000_000


@dataclass(frozen=True)
class Event:
    txn_ref: str
    amount_paise: int
    created_at: datetime
    event_type: str
    original_ref: str = ""


def _random_timestamp(rng: random.Random, day: date) -> datetime:
    """Bias some events toward late hours to exercise the T+2 cutoff."""
    if rng.random() < 0.35:
        hour = rng.randint(18, 23)
    else:
        hour = rng.randint(0, 17)
    return datetime(
        day.year,
        day.month,
        day.day,
        hour,
        rng.randrange(60),
        rng.randrange(60),
        tzinfo=IST,
    )


def _random_amount(rng: random.Random) -> int:
    """Mix ordinary paise values with exact half-paisa fee cases."""
    if rng.random() < 0.25:
        max_step = (MAX_AMOUNT_PAISE - 25) // 50
        steps = rng.randint(MIN_AMOUNT_PAISE // 50, max_step)
        return steps * 50 + 25
    return rng.randint(MIN_AMOUNT_PAISE, MAX_AMOUNT_PAISE)


def _dates(start: date, end: date) -> list[date]:
    day_count = (end - start).days + 1
    return [start + timedelta(days=offset) for offset in range(day_count)]


def generate_world(
    seed: int = settings.DEFAULT_SEED,
    october_payment_count: int = settings.OCTOBER_PAYMENT_COUNT,
    late_september_payment_count: int = settings.LATE_SEPTEMBER_PAYMENT_COUNT,
) -> list[Event]:
    """Generate payments and eligible full refunds inside the ledger window."""
    rng = random.Random(seed)
    october_days = _dates(settings.PERIOD_START, settings.PERIOD_END)
    september_days = _dates(settings.LEDGER_START, settings.PERIOD_START - timedelta(days=1))
    payments: list[Event] = []

    for count, eligible_days in (
        (late_september_payment_count, september_days),
        (october_payment_count, october_days),
    ):
        for _ in range(count):
            day = rng.choice(eligible_days)
            payments.append(
                Event(
                    txn_ref=f"TXN{len(payments) + 1:07d}",
                    amount_paise=_random_amount(rng),
                    created_at=_random_timestamp(rng, day),
                    event_type="payment",
                )
            )

    events = list(payments)
    for payment in payments:
        if rng.randrange(100) >= settings.REFUND_RATE_PERCENT:
            continue
        refund_day = payment.created_at.date() + timedelta(days=rng.randint(1, 10))
        if refund_day > settings.PERIOD_END:
            continue
        refund_ref = f"TXN{len(events) + 1:07d}"
        refund_created_at = _random_timestamp(rng, refund_day)
        events.append(
            Event(
                txn_ref=refund_ref,
                amount_paise=-payment.amount_paise,
                created_at=refund_created_at,
                event_type="refund",
                original_ref=payment.txn_ref,
            )
        )

    return sorted(events, key=lambda event: (event.created_at, event.txn_ref))
