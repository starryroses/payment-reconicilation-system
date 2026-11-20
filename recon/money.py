"""Exact currency conversions and fee rounding for INR amounts."""

from decimal import Decimal, InvalidOperation

from recon.settings import FEE_PERCENT, PERCENT_DENOMINATOR


def rupees_to_paise(value: str | Decimal) -> int:
    """Convert a rupee value to paise without accepting hidden fractions."""
    if isinstance(value, float):
        raise TypeError("money values must not be floats")
    if not isinstance(value, (str, Decimal)):
        raise TypeError("rupee value must be a string or Decimal")

    try:
        rupees = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid rupee amount: {value!r}") from exc

    if not rupees.is_finite():
        raise ValueError("rupee amount must be finite")
    if rupees.as_tuple().exponent < -2:
        raise ValueError("rupee amount must have at most 2 decimal places")

    paise = rupees * 100
    return int(paise)


def paise_to_rupees(paise: int) -> Decimal:
    """Represent integer paise as an exact Decimal with two rupee places."""
    if isinstance(paise, bool) or not isinstance(paise, int):
        raise TypeError("paise amount must be an integer")
    digits = tuple(int(digit) for digit in str(abs(paise)))
    return Decimal((int(paise < 0), digits, -2))


def fee_paise(amount_paise: int) -> int:
    """Round a non-negative 2% fee half-up using integer arithmetic."""
    if isinstance(amount_paise, bool) or not isinstance(amount_paise, int):
        raise TypeError("fee base must be an integer number of paise")
    if amount_paise < 0:
        raise ValueError("fee base must be non-negative")
    return (amount_paise * FEE_PERCENT + PERCENT_DENOMINATOR // 2) // PERCENT_DENOMINATOR
