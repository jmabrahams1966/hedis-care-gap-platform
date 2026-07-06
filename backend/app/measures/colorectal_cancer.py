from datetime import date, datetime
from typing import Any

from ..models import Member
from .base import Measure

SCHEDULING_HELP_WINDOW_DAYS = 14


class ColorectalCancerScreeningMeasure(Measure):
    """HEDIS Colorectal Cancer Screening (COL).

    Same self-report + scheduling-assistance shape as breast cancer screening:
    no licensed instrument, just a completion check and an offer to help
    schedule if the member hasn't been screened. Real HEDIS COL numerator
    credit is normally claims-based (FIT/FOBT, colonoscopy, sigmoidoscopy, or
    CT colonography each have different recency windows) — see
    docs/HEDIS_COMPLIANCE.md.
    """

    code = "colorectal_cancer"
    hedis_measure_name = "Colorectal Cancer Screening (COL)"
    description = (
        "Outreach to confirm colorectal cancer screening completion (FIT/FOBT, colonoscopy, "
        "sigmoidoscopy, or CT colonography) within the recommended interval, with scheduling "
        "assistance offered when a member hasn't been screened."
    )

    def is_eligible(self, member: Member, as_of: date) -> bool:
        try:
            dob = datetime.strptime(member.date_of_birth, "%Y-%m-%d").date()
        except ValueError:
            return False
        age = as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))
        return 45 <= age <= 75  # no sex restriction

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        has_completed = bool(payload["has_completed"])
        wants_scheduling_help = bool(payload.get("wants_scheduling_help", False))
        screening_type = payload.get("screening_type")  # e.g. "fit", "colonoscopy" — optional detail

        return {
            "numerator_met": has_completed,
            "safety_flag": False,
            "needs_follow_up": (not has_completed) and wants_scheduling_help,
            "instrument_scores": {
                "col": {
                    "has_completed": has_completed,
                    "screening_type": screening_type,
                    "wants_scheduling_help": wants_scheduling_help,
                }
            },
        }

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        return SCHEDULING_HELP_WINDOW_DAYS if evaluation.get("needs_follow_up") else None


colorectal_cancer_measure = ColorectalCancerScreeningMeasure()
