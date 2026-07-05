from datetime import date, datetime
from typing import Any

from ..models import Member
from ..scoring import score_gad7, score_phq9
from .base import Measure

MODERATE_OR_ABOVE = {"moderate", "moderately_severe", "severe"}


class MentalHealthMeasure(Measure):
    """HEDIS Depression Screening and Follow-Up (DSF), implemented with PHQ-9
    (primary screening + safety item) and GAD-7 (secondary, common comorbidity).

    Numerator is met when the member completes the screening. A PHQ-9 score in the
    moderate range or higher, or a positive safety item (Q9), additionally opens a
    follow-up requirement that the care manager queue tracks separately.
    """

    code = "mental_health"
    hedis_measure_name = "Depression Screening and Follow-Up (DSF)"
    description = (
        "Annual depression screening via PHQ-9 (+ GAD-7 for anxiety comorbidity) with "
        "documented follow-up for positive/moderate-or-higher results."
    )

    def is_eligible(self, member: Member, as_of: date) -> bool:
        try:
            dob = datetime.strptime(member.date_of_birth, "%Y-%m-%d").date()
        except ValueError:
            return False
        age = as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))
        return age >= 12  # DSF covers adolescents (12+) and adults

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        phq9 = score_phq9(payload["phq9"])
        gad7 = score_gad7(payload["gad7"]) if payload.get("gad7") else None

        safety_flag = phq9["safety_flag"]
        needs_follow_up = safety_flag or phq9["severity"] in MODERATE_OR_ABOVE

        return {
            "numerator_met": True,  # screening was completed
            "safety_flag": safety_flag,
            "needs_follow_up": needs_follow_up,
            "instrument_scores": {"phq9": phq9, "gad7": gad7},
        }

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        if not evaluation.get("needs_follow_up"):
            return None
        return 1 if evaluation.get("safety_flag") else 30


mental_health_measure = MentalHealthMeasure()
