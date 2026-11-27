"""Money helpers. Money is always ``Decimal``, rounded half-up to cents at the end of a sum."""

import re
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")

# Which ISO currencies each accepted symbol may stand for. A symbol that does not fit the file's
# currency is refused rather than silently dropped ("€38" in a USD file is not 38 USD).
SYMBOL_CURRENCIES: dict[str, frozenset[str]] = {
    "$": frozenset({"USD", "CAD", "AUD", "NZD", "SGD", "HKD"}),
    "€": frozenset({"EUR"}),
    "£": frozenset({"GBP"}),
    "₹": frozenset({"INR"}),
}

# One optional sign, one optional currency symbol, then ASCII digits with correctly grouped
# thousands commas (or none) and an optional fraction. Anything else is refused, not guessed.
_MONEY = re.compile(
    r"^(?P<sign>-)?(?P<symbol>[$€£₹])?\s*"
    r"(?P<num>[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$"
)


def to_money(x: Decimal) -> Decimal:
    """Round to cents, half-up."""
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_money_with_symbol(text: str) -> tuple[Decimal, str | None]:
    """Like ``parse_money`` but also return the currency symbol that was written, if any."""
    match = _MONEY.match(text.strip())
    if match is None:
        raise ValueError(f"not a money amount: {text[:40]!r}")
    value = Decimal(match["num"].replace(",", ""))
    return (-value if match["sign"] else value), match["symbol"]


def parse_money(text: str) -> Decimal:
    """Parse ``"38"``, ``"$1,234.50"``, ``"€0.99"``; raise ``ValueError`` for anything else."""
    return parse_money_with_symbol(text)[0]
