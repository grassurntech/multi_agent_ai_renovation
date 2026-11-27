"""Shared enums. Values are lowercase strings so they store and serialise cleanly."""

from enum import StrEnum


class Stage(StrEnum):
    """Unit lifecycle stage (design §3)."""

    DRAFT = "draft"
    ASSESSED = "assessed"
    PLANNED = "planned"
    AWAITING_AM_APPROVAL = "awaiting_am_approval"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    QA_REVIEW = "qa_review"
    READY_TO_LEASE = "ready_to_lease"


class Event(StrEnum):
    """Something that happened to a unit and may move its stage."""

    ASSESSOR_RUN = "assessor_run"
    PLANNER_RUN = "planner_run"
    SCOPE_SUBMITTED = "scope_submitted"
    AM_APPROVED = "am_approved"
    AM_REJECTED = "am_rejected"
    FIRST_PO_SIGNED = "first_po_signed"
    WORK_COMPLETED = "work_completed"
    QA_RUN = "qa_run"
    QA_PASSED = "qa_passed"
    QA_FAILED = "qa_failed"


class Grade(StrEnum):
    """Inventory quality grade."""

    GOOD = "good"
    BETTER = "better"
    BEST = "best"


_GRADE_RANK = {Grade.GOOD: 0, Grade.BETTER: 1, Grade.BEST: 2}


def grade_rank(g: Grade) -> int:
    """Return 0, 1 or 2 for good, better, best."""
    return _GRADE_RANK[g]


class Tier(StrEnum):
    """Impact bucket a scope line lands in."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Severity(StrEnum):
    """Issue severity reported by the Assessor."""

    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    SYSTEM_LEVEL = "system_level"
    SAFETY = "safety"


class LineVerdict(StrEnum):
    """QA judgement of one approved scope line."""

    DONE_AS_SPECIFIED = "done_as_specified"
    DONE_DIFFERENT_ITEM = "done_different_item"
    PARTIAL = "partial"
    MISSING = "missing"
    NOT_VERIFIABLE = "not_verifiable"


class QaResult(StrEnum):
    """Overall QA result."""

    PASS_ = "pass"
    FLAGGED = "flagged"
    NEEDS_EVIDENCE = "needs_evidence"


class EscalationKind(StrEnum):
    """Reason a unit is escalated to its PM."""

    SLIP = "slip"
    OVERSPEND = "overspend"
    BLOCKED = "blocked"
