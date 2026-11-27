import pytest

from reno_agents.inventory.loader import load_inventory, load_labor_rates
from reno_agents.inventory.schema import InventoryItem, LaborRate

HEADER = (
    "sku,category,subcategory,item_name,brand,model,spec,unit,unit_cost,currency,supplier,"
    "lead_time_days,grade,substitution_group,coverage_per_unit,coverage_unit,waste_pct,approved,"
    "approved_until"
)
PAINT = (
    "PNT-001,Paint,Interior wall,Eggshell wall paint,Northfield,NF-200,Eggshell white,gallon,"
    "38.00,USD,Acme Supply,2,better,PAINT-INT-WALL,350,sq_ft,10,Y,2027-12-31"
)
LABOR = (
    "task_code,category,task_name,unit,rate,currency,typical_hours_per_unit,trade\n"
    "L-PNT,Paint,Paint walls,sq_ft,1.25,USD,0.02,paint\n"
)


@pytest.fixture
def paint_item() -> InventoryItem:
    result = load_inventory(f"{HEADER}\n{PAINT}\n", currency="USD")
    assert result.ok
    return result.items[0]


@pytest.fixture
def paint_labor() -> LaborRate:
    result = load_labor_rates(LABOR, currency="USD")
    assert result.ok
    return result.items[0]
