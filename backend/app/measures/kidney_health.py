from datetime import date
from typing import Any

from ..models import Member
from .base import Measure, age_in_years

SCHEDULING_HELP_WINDOW_DAYS = 14


class KidneyHealthMeasure(Measure):
    """HEDIS Kidney Health Evaluation for Patients with Diabetes (KED).

    The other diabetes-bundle sub-measure. Condition-gated on diabetes, ages
    18–85. Unlike a single-test measure, the numerator requires BOTH tests in
    the measurement year: an eGFR (a blood test for kidney filtration) AND a
    uACR (a urine albumin-to-creatinine ratio) — one without the other does not
    meet the numerator. Self-report for outreach/tracking; claims confirmation
    is needed for real HEDIS credit.
    """

    code = "kidney_health"
    hedis_measure_name = "Kidney Health Evaluation for Patients with Diabetes (KED)"
    description = (
        "Outreach to members with diabetes to confirm both kidney-health tests within the "
        "measurement year — an eGFR (blood) and a uACR (urine) — with scheduling help when either is missing."
    )

    def is_eligible(self, member: Member, as_of: date) -> bool:
        if "diabetes" not in member.conditions:
            return False
        age = age_in_years(member.date_of_birth, as_of)
        return age is not None and 18 <= age <= 85

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Both tests are required for the numerator — this is the defining
        # feature of KED versus a single-lab measure like HbA1c.
        has_egfr = bool(payload["has_egfr"])
        has_uacr = bool(payload["has_uacr"])
        wants_scheduling_help = bool(payload.get("wants_scheduling_help", False))
        both_done = has_egfr and has_uacr

        return {
            "numerator_met": both_done,
            "safety_flag": False,
            "needs_follow_up": (not both_done) and wants_scheduling_help,
            "instrument_scores": {
                "ked": {
                    "has_egfr": has_egfr,
                    "has_uacr": has_uacr,
                    "wants_scheduling_help": wants_scheduling_help,
                }
            },
        }

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        return SCHEDULING_HELP_WINDOW_DAYS if evaluation.get("needs_follow_up") else None


kidney_health_measure = KidneyHealthMeasure()
