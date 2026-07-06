from datetime import date
from typing import Any

from .base import Demographic, Measure, age_in_years

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

    def is_eligible(self, subject: Demographic, as_of: date) -> bool:
        age = age_in_years(subject.date_of_birth, as_of)
        return age is not None and 45 <= age <= 75  # no sex restriction

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
