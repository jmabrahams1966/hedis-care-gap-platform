from datetime import date
from typing import Any

from .base import Demographic, Measure, age_in_years

SCHEDULING_HELP_WINDOW_DAYS = 14


class WellChildVisitsMeasure(Measure):
    """HEDIS Well-Child Visits (WCV).

    Dependent-scoped, like Childhood Immunization Status. Real HEDIS WCV
    covers a wider 0-21 age range with different visit-count requirements for
    younger age bands (e.g. 6+ visits by 15 months) — this module simplifies
    to a single "at least one well-child visit in the last 12 months"
    self-report for ages 3-17, matching the annual-checkup cadence that
    applies to most of the eligible population. Confirm against the current
    spec before relying on this — see docs/HEDIS_COMPLIANCE.md.
    """

    code = "well_child_visits"
    hedis_measure_name = "Well-Child Visits (WCV)"
    description = (
        "Outreach to a guardian to confirm their child's annual well-child visit (checkup) is "
        "complete, with scheduling assistance offered if not."
    )
    subject_type = "dependent"

    def is_eligible(self, subject: Demographic, as_of: date) -> bool:
        age = age_in_years(subject.date_of_birth, as_of)
        return age is not None and 3 <= age <= 17

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        has_completed = bool(payload["has_completed"])
        wants_scheduling_help = bool(payload.get("wants_scheduling_help", False))

        return {
            "numerator_met": has_completed,
            "safety_flag": False,
            "needs_follow_up": (not has_completed) and wants_scheduling_help,
            "instrument_scores": {
                "wcv": {"has_completed": has_completed, "wants_scheduling_help": wants_scheduling_help}
            },
        }

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        return SCHEDULING_HELP_WINDOW_DAYS if evaluation.get("needs_follow_up") else None


well_child_visits_measure = WellChildVisitsMeasure()
