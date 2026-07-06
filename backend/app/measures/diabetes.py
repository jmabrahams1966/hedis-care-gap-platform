from datetime import date
from typing import Any

from ..models import Member
from .base import Measure, age_in_years

FOLLOW_UP_DAYS = 30
POOR_CONTROL_THRESHOLD = 9.0


class DiabetesA1cMeasure(Measure):
    """HEDIS Comprehensive Diabetes Care: HbA1c Testing & Control (CDC subset).

    Covers only the HbA1c testing/control sub-measure of the full CDC bundle —
    eye exam and nephropathy monitoring are separate HEDIS sub-measures not
    implemented here (see docs/HEDIS_COMPLIANCE.md). Condition-gated like blood
    pressure. Numerator is "tested in the period"; an A1c above 9.0 (poor
    control) opens a follow-up even though the numerator itself only requires
    the test having been done, mirroring how a positive PHQ-9 opens follow-up
    independent of numerator status.
    """

    code = "diabetes_a1c"
    hedis_measure_name = "Comprehensive Diabetes Care: HbA1c Testing & Control (CDC)"
    description = (
        "Remote check-in for members with diabetes to confirm recent HbA1c testing and flag "
        "poor control for care manager follow-up."
    )

    def is_eligible(self, member: Member, as_of: date) -> bool:
        if "diabetes" not in member.conditions:
            return False
        age = age_in_years(member.date_of_birth, as_of)
        return age is not None and 18 <= age <= 75

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        has_recent_test = bool(payload["has_recent_test"])
        raw_value = payload.get("a1c_value")
        a1c_value = float(raw_value) if raw_value not in (None, "") else None
        poor_control = has_recent_test and a1c_value is not None and a1c_value > POOR_CONTROL_THRESHOLD

        return {
            "numerator_met": has_recent_test,
            "safety_flag": False,
            "needs_follow_up": (not has_recent_test) or poor_control,
            "instrument_scores": {
                "a1c": {"has_recent_test": has_recent_test, "value": a1c_value, "poor_control": poor_control}
            },
        }

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        return FOLLOW_UP_DAYS if evaluation.get("needs_follow_up") else None


diabetes_a1c_measure = DiabetesA1cMeasure()
