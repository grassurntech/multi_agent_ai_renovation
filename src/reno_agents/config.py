"""Runtime settings, read from ``RENO_*`` environment variables."""

from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from reno_agents.domain.enums import Grade


def _split_comma_list(value: Any) -> Any:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


class Settings(BaseSettings):
    """Every default comes from the design doc."""

    model_config = SettingsConfigDict(env_prefix="RENO_", env_file=None)

    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    approval_threshold: Decimal = Field(default=Decimal("15000"), ge=0, allow_inf_nan=False)
    preferred_grade: Grade = Grade.BETTER
    change_request_pct: Decimal = Field(default=Decimal("10"), ge=0, allow_inf_nan=False)
    low_confidence_threshold: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    blocked_alert_days: int = Field(default=2, ge=0)
    slip_alert_days: int = Field(default=7, ge=0)
    overspend_alert_pct: Decimal = Field(default=Decimal("10"), ge=0, allow_inf_nan=False)
    qa_deviation_pct: Decimal = Field(
        default=Decimal("10"), ge=0, lt=100, decimal_places=2, allow_inf_nan=False
    )
    hours_per_day: Decimal = Field(
        default=Decimal("8"), ge=Decimal("0.01"), le=24, allow_inf_nan=False
    )
    workdays: Annotated[frozenset[int], NoDecode] = frozenset({0, 1, 2, 3, 4})
    holidays: Annotated[frozenset[date], NoDecode] = frozenset()

    @field_validator(
        "approval_threshold",
        "change_request_pct",
        "low_confidence_threshold",
        "blocked_alert_days",
        "slip_alert_days",
        "overspend_alert_pct",
        "qa_deviation_pct",
        "hours_per_day",
        mode="before",
    )
    @classmethod
    def _ascii_numbers(cls, value: Any) -> Any:
        # Refuse look-alike digits such as full-width "１５０００" instead of reading them.
        if isinstance(value, str) and not value.strip().isascii():
            raise ValueError("numbers must be written with ASCII digits")
        return value

    @field_validator("workdays", "holidays", mode="before")
    @classmethod
    def _parse_comma_list(cls, value: Any) -> Any:
        return _split_comma_list(value)

    @field_validator("workdays")
    @classmethod
    def _check_workdays(cls, value: frozenset[int]) -> frozenset[int]:
        if not value:
            raise ValueError("at least one workday is required")
        bad = sorted(d for d in value if not 0 <= d <= 6)
        if bad:
            raise ValueError(f"workdays must be 0 (Mon) to 6 (Sun), got {bad}")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read once."""
    return Settings()
