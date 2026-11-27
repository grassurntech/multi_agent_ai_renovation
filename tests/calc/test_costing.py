from decimal import Decimal

import pytest

from reno_agents.calc.costing import (
    LineCost,
    MissingEstimate,
    change_request_needs_asset_manager,
    line_cost,
    needs_asset_manager_approval,
    purchase_quantity,
    tier_totals,
)
from reno_agents.domain.enums import Tier
from reno_agents.inventory.schema import InventoryItem, LaborRate


def test_paint_example_from_spec() -> None:
    assert purchase_quantity(Decimal("420"), Decimal("350"), Decimal("10")) == 2


def test_exact_coverage_does_not_round_up() -> None:
    assert purchase_quantity(Decimal("350"), Decimal("350"), Decimal("0")) == 1


def test_waste_that_lands_exactly_on_a_whole_unit_does_not_round_up() -> None:
    # 300 / 330 * 1.10 is exactly 1 gallon: it must not be rounded up to 2.
    assert purchase_quantity(Decimal("300"), Decimal("330"), Decimal("10")) == 1


@pytest.mark.parametrize(
    "measured,coverage,waste",
    [("0", "350", "10"), ("-5", "350", "10"), ("10", "0", "10"), ("10", "350", "-1")],
)
def test_bad_quantity_inputs_rejected(measured: str, coverage: str, waste: str) -> None:
    with pytest.raises(ValueError):
        purchase_quantity(Decimal(measured), Decimal(coverage), Decimal(waste))


def test_line_cost_materials_plus_labor(paint_item: InventoryItem, paint_labor: LaborRate) -> None:
    c = line_cost(Decimal("420"), paint_item, paint_labor)
    assert (c.purchase_qty, c.materials, c.labor, c.total) == (
        2,
        Decimal("76.00"),
        Decimal("525.00"),
        Decimal("601.00"),
    )


def test_line_cost_without_labor(paint_item: InventoryItem) -> None:
    c = line_cost(Decimal("420"), paint_item, None)
    assert (c.labor, c.total) == (Decimal("0.00"), Decimal("76.00"))


def test_procurement_needed_line_requires_estimate() -> None:
    with pytest.raises(MissingEstimate):
        line_cost(Decimal("1"), None, None)
    c = line_cost(Decimal("1"), None, None, estimate=Decimal("1200"))
    assert c.purchase_qty is None and c.total == Decimal("1200.00")


def test_negative_estimate_rejected() -> None:
    with pytest.raises(ValueError):
        line_cost(Decimal("1"), None, None, estimate=Decimal("-1"))


def test_tier_totals_include_empty_tiers() -> None:
    t = tier_totals([(Tier.HIGH, LineCost(1, Decimal("10"), Decimal("5"), Decimal("15")))])
    assert t == {
        Tier.HIGH: Decimal("15.00"),
        Tier.MEDIUM: Decimal("0.00"),
        Tier.LOW: Decimal("0.00"),
    }


def test_threshold_is_strictly_greater() -> None:
    assert not needs_asset_manager_approval(Decimal("15000.00"), Decimal("15000"))
    assert needs_asset_manager_approval(Decimal("15000.01"), Decimal("15000"))


@pytest.mark.parametrize(
    "orig,new,expected",
    [
        ("10000", "11000", False),  # +10% exactly, under threshold
        ("10000", "11000.01", True),  # just over 10%
        ("14000", "15001", True),  # crosses threshold with only a +7.15% increase
        ("20000", "20500", True),  # already over threshold: any change re-approved
    ],
)
def test_change_request_rule(orig: str, new: str, expected: bool) -> None:
    got = change_request_needs_asset_manager(
        Decimal(orig), Decimal(new), Decimal("15000"), Decimal("10")
    )
    assert got is expected
