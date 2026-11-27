from decimal import Decimal

import pytest

from reno_agents.calc.money import parse_money, to_money
from reno_agents.inventory.loader import load_inventory, load_labor_rates

HEADER = (
    "sku,category,subcategory,item_name,brand,model,spec,unit,unit_cost,currency,supplier,"
    "lead_time_days,grade,substitution_group,coverage_per_unit,coverage_unit,waste_pct,approved,"
    "approved_until"
)
PAINT = (
    "PNT-001,Paint,Interior wall,Eggshell wall paint,Northfield,NF-200,Eggshell white,gallon,"
    "38.00,USD,Acme Supply,2,better,PAINT-INT-WALL,350,sq_ft,10,Y,2027-12-31"
)
LABOR_HEADER = "task_code,category,task_name,unit,rate,currency,typical_hours_per_unit,trade"


def test_loads_valid_row() -> None:
    r = load_inventory(f"{HEADER}\n{PAINT}\n", currency="USD")
    assert r.ok and r.items[0].unit_cost == Decimal("38.00") and r.items[0].approved is True


def test_excel_quirks_accepted() -> None:
    row = PAINT.replace("38.00", '"$1,038.50"').replace(",Y,", ",y,")
    r = load_inventory(f"﻿{HEADER}\n{row}\n,,,,,,,,,,,,,,,,,,\n\n", currency="USD")
    assert r.ok and r.items[0].unit_cost == Decimal("1038.50")


def test_bad_cost_is_row_error_not_guess() -> None:
    r = load_inventory(f"{HEADER}\n{PAINT.replace('38.00', 'thirty')}\n", currency="USD")
    assert r.items == [] and r.errors[0].row == 2 and r.errors[0].field == "unit_cost"


def test_duplicate_sku_flagged_on_later_row() -> None:
    r = load_inventory(f"{HEADER}\n{PAINT}\n{PAINT}\n", currency="USD")
    assert len(r.items) == 1 and r.errors[0].row == 3 and r.errors[0].field == "sku"


def test_missing_column_rejects_file() -> None:
    r = load_inventory(HEADER.replace(",waste_pct", "") + "\n", currency="USD")
    assert r.items == [] and r.errors[0].row == 1 and "waste_pct" in r.errors[0].message


def test_currency_mismatch_is_error() -> None:
    r = load_inventory(f"{HEADER}\n{PAINT.replace('USD', 'EUR')}\n", currency="USD")
    assert r.errors[0].field == "currency"


def test_labor_trade_must_be_known() -> None:
    r = load_labor_rates(
        f"{LABOR_HEADER}\nL-PNT,Paint,Paint walls,sq_ft,1.25,USD,0.02,paint\n"
        "L-XXX,Other,Mystery,each,5,USD,1,plumbing_magic\n",
        currency="USD",
    )
    assert len(r.items) == 1 and r.errors[0].field == "trade"


@pytest.mark.parametrize("value", ["maybe", "true", "1", ""])
def test_approved_accepts_only_yes_no(value: str) -> None:
    r = load_inventory(f"{HEADER}\n{PAINT.replace(',Y,', f',{value},')}\n", currency="USD")
    assert r.items == [] and r.errors[0].field == "approved"


@pytest.mark.parametrize("value", ["yes", "NO", "n"])
def test_approved_yes_no_any_case(value: str) -> None:
    r = load_inventory(f"{HEADER}\n{PAINT.replace(',Y,', f',{value},')}\n", currency="USD")
    assert r.ok


def test_unquoted_thousands_comma_shifts_columns_and_is_rejected() -> None:
    r = load_inventory(f"{HEADER}\n{PAINT.replace('38.00', '$1,038.50')}\n", currency="USD")
    assert r.items == [] and r.errors and r.errors[0].row == 2


def test_formula_like_text_cell_rejected() -> None:
    row = PAINT.replace("Eggshell wall paint", '"=HYPERLINK(""http://x.invalid"",""x"")"')
    r = load_inventory(f"{HEADER}\n{row}\n", currency="USD")
    assert r.items == [] and r.errors[0].field == "item_name"


def test_nan_coverage_rejected() -> None:
    r = load_inventory(f"{HEADER}\n{PAINT.replace(',350,', ',NaN,')}\n", currency="USD")
    assert r.items == [] and r.errors[0].field == "coverage_per_unit"


def test_header_names_tolerate_case_and_spaces() -> None:
    header = HEADER.replace("sku,", " SKU ,")
    assert load_inventory(f"{header}\n{PAINT}\n", currency="USD").ok


@pytest.mark.parametrize(
    "text,expected",
    [
        ("38", "38"),
        (" $1,234.50 ", "1234.50"),
        ("€0.99", "0.99"),
        ("£12", "12"),
        ("₹1,000", "1000"),
    ],
)
def test_parse_money_accepts(text: str, expected: str) -> None:
    assert parse_money(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["thirty", "1,2,3", "12,34", "NaN", "Infinity", "1e5", "$$5", ""])
def test_parse_money_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        parse_money(text)


def test_to_money_rounds_half_up() -> None:
    assert to_money(Decimal("2.345")) == Decimal("2.35")
    assert to_money(Decimal("2.344")) == Decimal("2.34")
