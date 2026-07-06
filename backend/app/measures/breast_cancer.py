from datetime import date
from typing import Any

from .base import Demographic, Measure, age_in_years

SCHEDULING_HELP_WINDOW_DAYS = 14


class BreastCancerScreeningMeasure(Measure):
    """HEDIS Breast Cancer Screening (BCS).

    Unlike mental health, this isn't a self-administered instrument — the member
    is asked whether they've had a mammogram in the measurement period, and
    offered scheduling help if not. Self-report satisfies the numerator here for
    care-gap tracking purposes only; a real HEDIS submission for this measure
    typically requires claims-based confirmation (see docs/HEDIS_COMPLIANCE.md) —
    this module is a starting point for outreach, not a substitute for that.
    """

    code = "breast_cancer"
    hedis_measure_name = "Breast Cancer Screening (BCS)"
    description = (
        "Outreach to confirm mammogram completion within the measurement period, "
        "with scheduling assistance offered when a member hasn't been screened."
    )

    def is_eligible(self, subject: Demographic, as_of: date) -> bool:
        if subject.sex != "F":
            return False
        age = age_in_years(subject.date_of_birth, as_of)
        return age is not None and 50 <= age <= 74

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        has_completed = bool(payload["has_completed"])
        wants_scheduling_help = bool(payload.get("wants_scheduling_help", False))
        completed_date = payload.get("completed_date")

        return {
            "numerator_met": has_completed,
            "safety_flag": False,
            "needs_follow_up": (not has_completed) and wants_scheduling_help,
            "instrument_scores": {
                "bcs": {
                    "has_completed": has_completed,
                    "completed_date": completed_date,
                    "wants_scheduling_help": wants_scheduling_help,
                }
            },
        }

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        return SCHEDULING_HELP_WINDOW_DAYS if evaluation.get("needs_follow_up") else None


breast_cancer_measure = BreastCancerScreeningMeasure()
