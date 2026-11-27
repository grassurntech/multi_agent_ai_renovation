"""Row models for ``inventory.csv`` and ``labor_rates.csv`` (design §6)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from reno_agents.calc.money import parse_money
from reno_agents.calc.schedule import TRADE_ORDER
from reno_agents.domain.enums import Grade

# Cells starting with these are spreadsheet formulas; they are refused so a later CSV or
# spreadsheet export can never execute them.
_FORMULA_PREFIXES = ("=", "+", "@", "\t", "\r")
_YES = {"y", "yes"}
_NO = {"n", "no"}


def _check_text(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        raise ValueError("text must not start with = + @ or a control character")
    return value


def _money(value: Any) -> Any:
    return parse_money(value) if isinstance(value, str) else value


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _no_formulas(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
        return _check_text(value)


class InventoryItem(_Row):
    """One approved (or formerly approved) inventory item."""

    sku: str = Field(min_length=1)
    category: str = Field(min_length=1)
    subcategory: str
    item_name: str = Field(min_length=1)
    brand: str
    model: str
    spec: str
    unit: str = Field(min_length=1)
    unit_cost: Decimal = Field(ge=0, allow_inf_nan=False)
    currency: str = Field(min_length=1)
    supplier: str = Field(min_length=1)
    lead_time_days: int = Field(ge=0)
    grade: Grade
    substitution_group: str = Field(min_length=1)
    coverage_per_unit: Decimal = Field(gt=0, allow_inf_nan=False)
    coverage_unit: str = Field(min_length=1)
    waste_pct: Decimal = Field(ge=0, le=100, allow_inf_nan=False)
    approved: bool
    approved_until: date

    @field_validator("unit_cost", mode="before")
    @classmethod
    def _parse_cost(cls, value: Any) -> Any:
        return _money(value)

    @field_validator("currency", mode="after")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("grade", mode="before")
    @classmethod
    def _lower_grade(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("approved", mode="before")
    @classmethod
    def _parse_approved(cls, value: Any) -> Any:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in _YES:
            return True
        if text in _NO:
            return False
        raise ValueError("approved must be Y or N")

    @field_validator("approved_until", mode="before")
    @classmethod
    def _iso_date(cls, value: Any) -> Any:
        if isinstance(value, str):
            return date.fromisoformat(value.strip())
        return value


class LaborRate(_Row):
    """Labor price per unit of work, plus typical hours per unit for durations."""

    task_code: str = Field(min_length=1)
    category: str = Field(min_length=1)
    task_name: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    rate: Decimal = Field(ge=0, allow_inf_nan=False)
    currency: str = Field(min_length=1)
    typical_hours_per_unit: Decimal = Field(ge=0, allow_inf_nan=False)
    trade: str

    @field_validator("rate", mode="before")
    @classmethod
    def _parse_rate(cls, value: Any) -> Any:
        return _money(value)

    @field_validator("currency", mode="after")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("trade", mode="after")
    @classmethod
    def _known_trade(cls, value: str) -> str:
        trade = value.lower()
        if trade not in TRADE_ORDER:
            raise ValueError(f"trade must be one of {', '.join(TRADE_ORDER)}")
        return trade


@dataclass(frozen=True)
class RowError:
    """A problem in one CSV row. ``row`` is the 1-based line number; the header is line 1."""

    row: int
    field: str | None
    message: str


T = TypeVar("T")


@dataclass
class LoadResult(Generic[T]):
    """Valid rows plus every row error. Rows with any error are left out of ``items``."""

    items: list[T]
    errors: list[RowError]

    @property
    def ok(self) -> bool:
        return not self.errors
