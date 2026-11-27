"""Money helpers. Money is always ``Decimal``, rounded half-up to cents at the end of a sum."""

import re
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")

# One optional sign, one optional currency symbol, then digits with correctly grouped
# thousands commas (or none) and an optional fraction. Anything else is refused, not guessed.
_MONEY = re.compile(
    r"^(?P<sign>-)?[$€£₹]?\s*(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)$"
)


def to_money(x: Decimal) -> Decimal:
    """Round to cents, half-up."""
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_money(text: str) -> Decimal:
    """Parse ``"38"``, ``"$1,234.50"``, ``"€0.99"``; raise ``ValueError`` for anything else."""
    match = _MONEY.match(text.strip())
    if match is None:
        raise ValueError(f"not a money amount: {text!r}")
    value = Decimal(match["num"].replace(",", ""))
    return -value if match["sign"] else value
