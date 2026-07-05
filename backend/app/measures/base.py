from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any

from ..models import Member


class Measure(ABC):
    """A pluggable HEDIS measure module.

    Adding a new measure domain (breast cancer screening, colorectal cancer
    screening, etc.) means implementing this interface and registering it in
    app/measures/__init__.py — no changes to tenant, member, or care-gap schema.
    """

    code: str
    hedis_measure_name: str
    description: str

    @abstractmethod
    def is_eligible(self, member: Member, as_of: date) -> bool:
        """Whether this member falls in the measure's eligible population."""

    @abstractmethod
    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Score a member's submitted response. Returns dict with at least
        `numerator_met` (bool) and `safety_flag` (bool), plus measure-specific detail
        to store on ScreeningSubmission.instrument_scores.
        """

    @abstractmethod
    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        """Days after a positive/at-risk result within which follow-up must be
        documented for HEDIS credit. None if this result doesn't require follow-up.
        """


def default_period(as_of: date | None = None) -> str:
    return str((as_of or datetime.utcnow().date()).year)
