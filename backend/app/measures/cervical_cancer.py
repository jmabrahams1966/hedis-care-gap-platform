from datetime import date
from typing import Any

from .base import Demographic, Measure, age_in_years

SCHEDULING_HELP_WINDOW_DAYS = 14


class CervicalCancerScreeningMeasure(Measure):
    """HEDIS Cervical Cancer Screening (CCS).

    The third leg of the screening trio alongside Breast (BCS) and Colorectal
    (COL). Eligible population is women 21–64. Real HEDIS credit is a rolling
    lookback — cervical cytology within the last 3 years (ages 21–64), or
    hrHPV/co-testing within the last 5 years (ages 30–64) — which the
    calendar-year `CareGap.period` doesn't model (the same limitation flagged
    for BCS/COL in docs/HEDIS_COMPLIANCE.md). Numerator here is self-report of a
    completed screening, for outreach and gap tracking; claims confirmation is
    needed for reportable credit.
    """

    code = "cervical_cancer"
    hedis_measure_name = "Cervical Cancer Screening (CCS)"
    description = (
        "Outreach to women 21–64 to confirm a cervical cancer screening (Pap and/or HPV test), "
        "with scheduling assistance offered when they're overdue."
    )
    # A hysterectomy with no residual cervix removes a member from the denominator.
    exclusion_codes = frozenset({"hysterectomy"})

    def is_eligible(self, subject: Demographic, as_of: date) -> bool:
        if subject.sex != "F":
            return False
        age = age_in_years(subject.date_of_birth, as_of)
        return age is not None and 21 <= age <= 64

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        has_completed = bool(payload["has_completed"])
        wants_scheduling_help = bool(payload.get("wants_scheduling_help", False))
        completed_date = payload.get("completed_date")

        return {
            "numerator_met": has_completed,
            "safety_flag": False,
            "needs_follow_up": (not has_completed) and wants_scheduling_help,
            "instrument_scores": {
                "ccs": {
                    "has_completed": has_completed,
                    "completed_date": completed_date,
                    "wants_scheduling_help": wants_scheduling_help,
                }
            },
        }

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        return SCHEDULING_HELP_WINDOW_DAYS if evaluation.get("needs_follow_up") else None


cervical_cancer_measure = CervicalCancerScreeningMeasure()
