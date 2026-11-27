"""Row models for ``inventory.csv`` and ``labor_rates.csv`` (design §6).

Every cell is either read exactly or refused with an error. Nothing is guessed.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from reno_agents.calc.money import parse_money
from reno_agents.calc.schedule import TRADE_ORDER
from reno_agents.domain.enums import Grade

# Cells starting with these are spreadsheet formulas (OWASP CSV injection list); they are refused
# so a later CSV or spreadsheet export can never execute them.
_FORMULA_PREFIXES = ("=", "+", "-", "@")
TEXT_MAX_LENGTH = 300
# Upper bounds keep every later calculation finite and fast; real inventory is far below them.
MAX_UNIT_COST = Decimal("1000000")
MAX_RATE = Decimal("100000")
MAX_COVERAGE = Decimal("1000000")
MAX_HOURS_PER_UNIT = Decimal("1000")
MAX_LEAD_TIME_DAYS = 3650
_YES = {"y", "yes"}
_NO = {"n", "no"}
_DECIMAL_TEXT = re.compile(r"^[0-9]+(?:\.[0-9]{1,6})?$")
_INT_TEXT = re.compile(r"^[0-9]+$")
_DATE_TEXT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def check_text(value: str) -> str:
    """Refuse formula-like and control-character text; return it stripped."""
    value = value.strip()
    if value.startswith(_FORMULA_PREFIXES):
        raise ValueError("text must not start with = + - or @ (spreadsheet formula)")
    if any(unicodedata.category(ch) == "Cc" for ch in value):
        raise ValueError("text must not contain control characters or line breaks")
    if len(value) > TEXT_MAX_LENGTH:
        raise ValueError(f"text is longer than {TEXT_MAX_LENGTH} characters")
    return value


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Fields whose text is money (may carry a currency symbol).
    MONEY_FIELDS: ClassVar[tuple[str, ...]] = ()

    @field_validator("*", mode="before")
    @classmethod
    def _strict_cells(cls, value: Any, info: ValidationInfo) -> Any:
        if not isinstance(value, str) or info.field_name is None:
            return value
        annotation = cls.model_fields[info.field_name].annotation
        if info.field_name in cls.MONEY_FIELDS:
            return parse_money(value)
        if annotation is str:
            return check_text(value)
        text = value.strip()
        if annotation is Decimal and not _DECIMAL_TEXT.match(text):
            raise ValueError("must be a plain number like 350 or 0.25")
        if annotation is int and not _INT_TEXT.match(text):
            raise ValueError("must be a whole number like 3")
        if annotation is date:
            if not _DATE_TEXT.match(text):
                raise ValueError("must be a date written YYYY-MM-DD")
            return date.fromisoformat(text)
        return text


class InventoryItem(_Row):
    """One approved (or formerly approved) inventory item."""

    MONEY_FIELDS: ClassVar[tuple[str, ...]] = ("unit_cost",)

    sku: str = Field(min_length=1)
    category: str = Field(min_length=1)
    subcategory: str
    item_name: str = Field(min_length=1)
    brand: str
    model: str
    spec: str
    unit: str = Field(min_length=1)
    unit_cost: Decimal = Field(ge=0, le=MAX_UNIT_COST, allow_inf_nan=False)
    currency: str = Field(min_length=1)
    supplier: str = Field(min_length=1)
    lead_time_days: int = Field(ge=0, le=MAX_LEAD_TIME_DAYS)
    grade: Grade
    substitution_group: str = Field(min_length=1)
    coverage_per_unit: Decimal = Field(gt=0, le=MAX_COVERAGE, allow_inf_nan=False)
    coverage_unit: str = Field(min_length=1)
    waste_pct: Decimal = Field(ge=0, le=100, allow_inf_nan=False)
    approved: bool
    approved_until: date

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


class LaborRate(_Row):
    """Labor price per unit of work, plus typical hours per unit for durations."""

    MONEY_FIELDS: ClassVar[tuple[str, ...]] = ("rate",)

    task_code: str = Field(min_length=1)
    category: str = Field(min_length=1)
    task_name: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    rate: Decimal = Field(ge=0, le=MAX_RATE, allow_inf_nan=False)
    currency: str = Field(min_length=1)
    typical_hours_per_unit: Decimal = Field(ge=0, le=MAX_HOURS_PER_UNIT, allow_inf_nan=False)
    trade: str

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
    """A problem in one CSV row. ``row`` is the 1-based line the row starts on; header = 1."""

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
