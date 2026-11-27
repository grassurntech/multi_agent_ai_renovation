"""Runtime settings, read from ``RENO_*`` environment variables."""

from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from reno_agents.domain.enums import Grade


def _split_comma_list(value: Any) -> Any:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


class Settings(BaseSettings):
    """Every default comes from the design doc."""

    model_config = SettingsConfigDict(env_prefix="RENO_", env_file=None)

    currency: str = "USD"
    approval_threshold: Decimal = Decimal("15000")
    preferred_grade: Grade = Grade.BETTER
    change_request_pct: Decimal = Decimal("10")
    low_confidence_threshold: float = 0.5
    blocked_alert_days: int = 2
    slip_alert_days: int = 7
    overspend_alert_pct: Decimal = Decimal("10")
    qa_deviation_pct: Decimal = Decimal("10")
    hours_per_day: Decimal = Decimal("8")
    workdays: Annotated[frozenset[int], NoDecode] = frozenset({0, 1, 2, 3, 4})
    holidays: Annotated[frozenset[date], NoDecode] = frozenset()

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
