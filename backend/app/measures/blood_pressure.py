from datetime import date
from typing import Any

from ..models import Member
from .base import Measure, age_in_years

CRISIS_FOLLOW_UP_DAYS = 1
UNCONTROLLED_FOLLOW_UP_DAYS = 14


class ControllingBloodPressureMeasure(Measure):
    """HEDIS Controlling High Blood Pressure (CBP).

    Eligibility is condition-gated (member.conditions must include
    "hypertension") rather than just age-based — this is the first measure
    module where eligibility depends on clinical history, not demographics
    alone. Numerator is a self-reported home BP reading; a systolic/diastolic
    at or above 180/120 (hypertensive crisis territory) sets the same
    safety_flag/1-day-follow-up pattern PHQ-9's item 9 uses. Real HEDIS CBP
    numerator credit needs a clinician-confirmed reading, not member
    self-report alone — see docs/HEDIS_COMPLIANCE.md.
    """

    code = "blood_pressure"
    hedis_measure_name = "Controlling High Blood Pressure (CBP)"
    description = (
        "Remote BP check-ins for members with hypertension — self-reported readings flag "
        "anyone above goal (or in crisis range) for care manager follow-up."
    )

    def is_eligible(self, member: Member, as_of: date) -> bool:
        if "hypertension" not in member.conditions:
            return False
        age = age_in_years(member.date_of_birth, as_of)
        return age is not None and 18 <= age <= 85

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        systolic = int(payload["systolic"])
        diastolic = int(payload["diastolic"])
        if not (50 <= systolic <= 300 and 30 <= diastolic <= 200):
            raise ValueError("BP reading out of plausible range")

        controlled = systolic < 140 and diastolic < 90
        crisis = systolic >= 180 or diastolic >= 120

        return {
            "numerator_met": controlled,
            "safety_flag": crisis,
            "needs_follow_up": crisis or not controlled,
            "instrument_scores": {
                "bp": {"systolic": systolic, "diastolic": diastolic, "controlled": controlled, "crisis": crisis}
            },
        }

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        if evaluation.get("safety_flag"):
            return CRISIS_FOLLOW_UP_DAYS
        return UNCONTROLLED_FOLLOW_UP_DAYS if evaluation.get("needs_follow_up") else None


blood_pressure_measure = ControllingBloodPressureMeasure()
