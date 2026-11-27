"""Working-day calendar and trade-ordered schedule (design §5.3)."""

# Trade steps run in this order; tasks within one step run in parallel.
TRADE_ORDER: tuple[str, ...] = (
    "demo",
    "rough_in",
    "repairs",
    "paint",
    "flooring",
    "fixtures_appliances",
    "hardware",
    "clean",
)
