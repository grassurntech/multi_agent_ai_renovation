from datetime import date
from pathlib import Path

from reno_agents.calc.schedule import TRADE_ORDER
from reno_agents.inventory.catalog import Catalog
from reno_agents.inventory.loader import load_inventory, load_labor_rates
from reno_agents.inventory.schema import InventoryItem

D = Path(__file__).resolve().parents[1] / "data" / "sample"
TODAY = date(2026, 11, 27)
CATEGORIES = {
    "Paint",
    "Flooring",
    "Appliance",
    "Fixture",
    "Hardware",
    "Lighting",
    "Electrical",
    "Plumbing",
    "Cabinetry",
}


def _inventory() -> list[InventoryItem]:
    return load_inventory((D / "inventory.csv").read_text(), currency="USD").items


def test_sample_inventory_loads_without_errors() -> None:
    r = load_inventory((D / "inventory.csv").read_text(), currency="USD")
    assert r.errors == [] and 55 <= len(r.items) <= 70


def test_every_group_has_three_active_items() -> None:
    groups = Catalog(_inventory()).groups(TODAY)
    counts = {k: len(v) for k, v in groups.items()}
    assert groups and all(n >= 3 for n in counts.values()), counts


def test_sample_includes_filter_cases() -> None:
    items = _inventory()
    assert sum(not i.approved for i in items) == 1
    assert sum(i.approved and i.approved_until < TODAY for i in items) == 1
    assert any(i.substitution_group == "ELEC-PANEL" for i in items)
    assert any(i.substitution_group == "ELEC-SWITCH" for i in items)


def test_sample_covers_every_design_category() -> None:
    assert {i.category for i in _inventory()} == CATEGORIES


def test_sample_labor_loads_and_covers_every_trade() -> None:
    r = load_labor_rates((D / "labor_rates.csv").read_text(), currency="USD")
    assert r.errors == [] and len(r.items) >= 10
    assert {rate.trade for rate in r.items} == set(TRADE_ORDER)
