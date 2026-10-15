"""Decimal helpers. Financial arithmetic in CMRS never touches float."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def to_money(value) -> Decimal:
    if isinstance(value, float):
        raise TypeError("Refusing to convert a float to money; pass a str or Decimal.")
    try:
        return Decimal(value if value is not None else 0).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"Invalid amount: {value!r}") from exc


def quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
