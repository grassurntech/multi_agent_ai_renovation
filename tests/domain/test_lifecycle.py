from decimal import Decimal

import pytest

from reno_agents.domain.enums import Event as E
from reno_agents.domain.enums import Stage as S
from reno_agents.domain.lifecycle import GuardFailed, InvalidTransition, allowed_events, transition
from reno_agents.domain.lifecycle import TransitionContext as Ctx

T = Decimal("15000")


@pytest.mark.parametrize(
    "frm,ev,to",
    [
        (S.DRAFT, E.ASSESSOR_RUN, S.ASSESSED),
        (S.ASSESSED, E.ASSESSOR_RUN, S.ASSESSED),
        (S.ASSESSED, E.PLANNER_RUN, S.PLANNED),
        (S.PLANNED, E.PLANNER_RUN, S.PLANNED),
        (S.AWAITING_AM_APPROVAL, E.AM_APPROVED, S.APPROVED),
        (S.AWAITING_AM_APPROVAL, E.AM_REJECTED, S.PLANNED),
        (S.APPROVED, E.FIRST_PO_SIGNED, S.IN_PROGRESS),
        (S.COMPLETE, E.QA_RUN, S.QA_REVIEW),
        (S.QA_REVIEW, E.QA_PASSED, S.READY_TO_LEASE),
        (S.QA_REVIEW, E.QA_FAILED, S.IN_PROGRESS),
    ],
)
def test_valid_transitions(frm: S, ev: E, to: S) -> None:
    assert transition(frm, ev) is to


def test_scope_exactly_at_threshold_is_pm_approved() -> None:
    assert transition(S.PLANNED, E.SCOPE_SUBMITTED, Ctx(Decimal("15000.00"), T)) is S.APPROVED


def test_scope_over_threshold_needs_asset_manager() -> None:
    to = transition(S.PLANNED, E.SCOPE_SUBMITTED, Ctx(Decimal("15000.01"), T))
    assert to is S.AWAITING_AM_APPROVAL


def test_scope_submit_without_totals_fails_guard() -> None:
    with pytest.raises(GuardFailed):
        transition(S.PLANNED, E.SCOPE_SUBMITTED)


def test_work_completed_requires_after_media_per_room() -> None:
    with pytest.raises(GuardFailed) as exc:
        transition(
            S.IN_PROGRESS, E.WORK_COMPLETED, Ctx(rooms_missing_after_media=frozenset({"Kitchen"}))
        )
    assert "Kitchen" in " ".join(exc.value.reasons)
    assert transition(S.IN_PROGRESS, E.WORK_COMPLETED, Ctx()) is S.COMPLETE


@pytest.mark.parametrize(
    "frm,ev",
    [
        (S.PLANNED, E.ASSESSOR_RUN),
        (S.DRAFT, E.PLANNER_RUN),
        (S.APPROVED, E.QA_RUN),
        (S.READY_TO_LEASE, E.QA_FAILED),
        (S.IN_PROGRESS, E.FIRST_PO_SIGNED),
    ],
)
def test_invalid_transitions(frm: S, ev: E) -> None:
    with pytest.raises(InvalidTransition):
        transition(frm, ev)


def test_allowed_events_lists_guarded_events() -> None:
    assert allowed_events(S.PLANNED) == frozenset({E.PLANNER_RUN, E.SCOPE_SUBMITTED})
    assert allowed_events(S.IN_PROGRESS) == frozenset({E.WORK_COMPLETED})
    assert allowed_events(S.READY_TO_LEASE) == frozenset()
