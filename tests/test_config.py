from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from reno_agents.config import Settings
from reno_agents.domain.enums import Grade, grade_rank


def test_defaults_match_spec() -> None:
    s = Settings()
    assert s.currency == "USD"
    assert s.approval_threshold == Decimal("15000")
    assert s.preferred_grade is Grade.BETTER
    assert s.change_request_pct == Decimal("10")
    assert s.low_confidence_threshold == 0.5
    assert (s.blocked_alert_days, s.slip_alert_days) == (2, 7)
    assert s.overspend_alert_pct == s.qa_deviation_pct == Decimal("10")
    assert s.hours_per_day == Decimal("8")
    assert s.workdays == frozenset({0, 1, 2, 3, 4})
    assert s.holidays == frozenset()


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENO_APPROVAL_THRESHOLD", "20000")
    monkeypatch.setenv("RENO_WORKDAYS", "0,1,2,3,4,5")
    monkeypatch.setenv("RENO_HOLIDAYS", "2026-12-25,2027-01-01")
    s = Settings()
    assert s.approval_threshold == Decimal("20000")
    assert 5 in s.workdays
    assert date(2026, 12, 25) in s.holidays


def test_invalid_workday_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENO_WORKDAYS", "0,7")
    with pytest.raises(ValidationError):
        Settings()


def test_grade_rank_order() -> None:
    assert [grade_rank(g) for g in (Grade.GOOD, Grade.BETTER, Grade.BEST)] == [0, 1, 2]
