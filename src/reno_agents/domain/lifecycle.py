"""Unit lifecycle state machine (design §3).

The web app owns stage changes; agents never move a unit on their own. This module only answers
"given this stage and this event, what is the next stage?" and refuses anything else.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from reno_agents.domain.enums import Event, Stage


@dataclass(frozen=True)
class TransitionContext:
    """Facts a guarded transition needs. Unused fields stay at their defaults."""

    scope_total: Decimal | None = None
    approval_threshold: Decimal | None = None
    rooms_missing_after_media: frozenset[str] = field(default_factory=frozenset)


class InvalidTransition(Exception):
    """The event is not allowed from this stage."""

    def __init__(self, stage: Stage, event: Event) -> None:
        super().__init__(f"event {event.value!r} is not allowed from stage {stage.value!r}")
        self.stage = stage
        self.event = event


class GuardFailed(Exception):
    """The event is allowed from this stage, but a precondition is not met."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


_STATIC: dict[tuple[Stage, Event], Stage] = {
    (Stage.DRAFT, Event.ASSESSOR_RUN): Stage.ASSESSED,
    (Stage.ASSESSED, Event.ASSESSOR_RUN): Stage.ASSESSED,
    (Stage.ASSESSED, Event.PLANNER_RUN): Stage.PLANNED,
    (Stage.PLANNED, Event.PLANNER_RUN): Stage.PLANNED,
    (Stage.AWAITING_AM_APPROVAL, Event.AM_APPROVED): Stage.APPROVED,
    (Stage.AWAITING_AM_APPROVAL, Event.AM_REJECTED): Stage.PLANNED,
    (Stage.APPROVED, Event.FIRST_PO_SIGNED): Stage.IN_PROGRESS,
    (Stage.COMPLETE, Event.QA_RUN): Stage.QA_REVIEW,
    (Stage.QA_REVIEW, Event.QA_PASSED): Stage.READY_TO_LEASE,
    (Stage.QA_REVIEW, Event.QA_FAILED): Stage.IN_PROGRESS,
}
_GUARDED: frozenset[tuple[Stage, Event]] = frozenset(
    {
        (Stage.PLANNED, Event.SCOPE_SUBMITTED),
        (Stage.IN_PROGRESS, Event.WORK_COMPLETED),
    }
)
_NO_CONTEXT = TransitionContext()


def allowed_events(stage: Stage) -> frozenset[Event]:
    """Events that may be applied to a unit in ``stage`` (guards may still refuse them)."""
    return frozenset(ev for (st, ev) in (*_STATIC, *_GUARDED) if st is stage)


def transition(stage: Stage, event: Event, ctx: TransitionContext = _NO_CONTEXT) -> Stage:
    """Return the stage after ``event``, or raise ``InvalidTransition`` / ``GuardFailed``."""
    key = (stage, event)
    if key in _STATIC:
        return _STATIC[key]
    if key == (Stage.PLANNED, Event.SCOPE_SUBMITTED):
        return _submit_scope(ctx)
    if key == (Stage.IN_PROGRESS, Event.WORK_COMPLETED):
        return _complete_work(ctx)
    raise InvalidTransition(stage, event)


def _submit_scope(ctx: TransitionContext) -> Stage:
    reasons = []
    if ctx.scope_total is None:
        reasons.append("scope total is required to submit a scope")
    elif ctx.scope_total < 0:
        reasons.append("scope total cannot be negative")
    if ctx.approval_threshold is None:
        reasons.append("approval threshold is required to submit a scope")
    if reasons:
        raise GuardFailed(reasons)
    assert ctx.scope_total is not None and ctx.approval_threshold is not None
    # "More than the threshold" needs the asset manager; exactly at it is a PM approval.
    if ctx.scope_total > ctx.approval_threshold:
        return Stage.AWAITING_AM_APPROVAL
    return Stage.APPROVED


def _complete_work(ctx: TransitionContext) -> Stage:
    if ctx.rooms_missing_after_media:
        rooms = ", ".join(sorted(ctx.rooms_missing_after_media))
        raise GuardFailed([f"no 'after' media yet for rooms with approved scope: {rooms}"])
    return Stage.COMPLETE
