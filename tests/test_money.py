from decimal import Decimal

import pytest

from recon.money import fee_paise, paise_to_rupees, rupees_to_paise


@pytest.mark.parametrize(
    ("paise", "rupees"),
    [
        (0, Decimal("0.00")),
        (1, Decimal("0.01")),
        (123456, Decimal("1234.56")),
        (-123456, Decimal("-1234.56")),
    ],
)
def test_paise_rupee_round_trip(paise: int, rupees: Decimal) -> None:
    assert paise_to_rupees(paise) == rupees
    assert rupees_to_paise(rupees) == paise


@pytest.mark.parametrize("value", ["1.001", Decimal("1.001"), "-0.125"])
def test_rupees_to_paise_rejects_more_than_two_decimal_places(value: str | Decimal) -> None:
    with pytest.raises(ValueError, match="at most 2 decimal places"):
        rupees_to_paise(value)


def test_rupees_to_paise_rejects_float() -> None:
    with pytest.raises(TypeError, match="must not be floats"):
        rupees_to_paise(1.25)  # type: ignore[arg-type]


@pytest.mark.parametrize(("amount", "expected"), [(25, 1), (75, 2), (125, 3)])
def test_fee_uses_half_up_integer_rounding(amount: int, expected: int) -> None:
    # 25 paise at 2% is exactly half a paisa; Python round(0.5) would give 0.
    assert fee_paise(amount) == expected


def test_money_helpers_reject_non_integer_paise() -> None:
    with pytest.raises(TypeError):
        paise_to_rupees(1.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        fee_paise(25.0)  # type: ignore[arg-type]
