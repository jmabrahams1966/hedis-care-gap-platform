from datetime import date
from typing import Any

from .base import Demographic, Measure, age_in_years

SCHEDULING_HELP_WINDOW_DAYS = 14


class ChildhoodImmunizationMeasure(Measure):
    """HEDIS Childhood Immunization Status (CIS).

    First dependent-scoped measure (subject_type = "dependent") — the person
    being screened is the guardian's child, not the guardian answering the
    outreach. Real HEDIS CIS eligibility is children turning 2 during the
    measurement year; numerator is completion of a specific combination of
    vaccine doses ("Combo 10" etc.), which requires immunization record data
    this platform doesn't have. This module is a simplified self-report +
    scheduling-assist proxy — see docs/HEDIS_COMPLIANCE.md.
    """

    code = "childhood_immunization"
    hedis_measure_name = "Childhood Immunization Status (CIS)"
    description = (
        "Outreach to a guardian to confirm their 2-year-old's recommended immunizations are "
        "up to date, with scheduling assistance offered if not."
    )
    subject_type = "dependent"

    def is_eligible(self, subject: Demographic, as_of: date) -> bool:
        age = age_in_years(subject.date_of_birth, as_of)
        return age == 2

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        has_completed = bool(payload["has_completed"])
        wants_scheduling_help = bool(payload.get("wants_scheduling_help", False))

        return {
            "numerator_met": has_completed,
            "safety_flag": False,
            "needs_follow_up": (not has_completed) and wants_scheduling_help,
            "instrument_scores": {
                "cis": {"has_completed": has_completed, "wants_scheduling_help": wants_scheduling_help}
            },
        }

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        return SCHEDULING_HELP_WINDOW_DAYS if evaluation.get("needs_follow_up") else None


childhood_immunization_measure = ChildhoodImmunizationMeasure()
