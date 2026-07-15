from datetime import date
from typing import Any

from ..models import Member
from .base import Measure, age_in_years

SCHEDULING_HELP_WINDOW_DAYS = 14


class EyeExamMeasure(Measure):
    """HEDIS Eye Exam for Patients with Diabetes (EED).

    One of the diabetes-bundle sub-measures that sit alongside the HbA1c measure
    (`diabetes_a1c`). Condition-gated on diabetes, ages 18–75. Numerator is a
    retinal / dilated eye exam by an eye-care professional in the measurement
    year. Like the screening measures this is self-report for outreach/tracking;
    real HEDIS credit needs claims/encounter confirmation (see
    docs/HEDIS_COMPLIANCE.md), which staff can attach via the confirm-numerator
    action.
    """

    code = "eye_exam"
    hedis_measure_name = "Eye Exam for Patients with Diabetes (EED)"
    description = (
        "Outreach to members with diabetes to confirm a diabetic retinal eye exam within the "
        "measurement year, with scheduling assistance offered when one hasn't been done."
    )

    def is_eligible(self, member: Member, as_of: date) -> bool:
        if "diabetes" not in member.conditions:
            return False
        age = age_in_years(member.date_of_birth, as_of)
        return age is not None and 18 <= age <= 75

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        has_completed = bool(payload["has_completed"])
        wants_scheduling_help = bool(payload.get("wants_scheduling_help", False))
        completed_date = payload.get("completed_date")

        return {
            "numerator_met": has_completed,
            "safety_flag": False,
            "needs_follow_up": (not has_completed) and wants_scheduling_help,
            "instrument_scores": {
                "eed": {
                    "has_completed": has_completed,
                    "completed_date": completed_date,
                    "wants_scheduling_help": wants_scheduling_help,
                }
            },
        }

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        return SCHEDULING_HELP_WINDOW_DAYS if evaluation.get("needs_follow_up") else None


eye_exam_measure = EyeExamMeasure()
