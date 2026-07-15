"""Prenatal and Postpartum Care (PPC) — HEDIS reports this as two rates, so we
model it as two measures, both keyed to a delivery *episode* rather than the
calendar year:

- **ppc_prenatal** — a timely prenatal visit (in the first trimester or within
  42 days of enrollment).
- **ppc_postpartum** — a postpartum visit on or between 7 and 84 days after
  delivery.

Both are `data_driven` (opened when a `PregnancyEpisode` is ingested, not by the
demographic pass — see app/measures/ppc_service.py) but, unlike PDC, they
`accepts_self_report`: the member can still answer "yes, I had my visit," which
sets a self_report numerator that staff/claims can later upgrade.

Caveat: the prenatal indicator is only prospectively actionable if the platform
learns of the pregnancy during it (via `estimated_due_date`). When an episode is
ingested at/after delivery, the prenatal window has passed and ppc_prenatal
becomes a tracking/claims-confirmation item rather than an outreach nudge — the
postpartum indicator is the prospectively actionable one. See
docs/HEDIS_COMPLIANCE.md.
"""

from datetime import date
from typing import Any

from .base import Demographic, Measure, age_in_years

POSTPARTUM_SCHEDULING_WINDOW_DAYS = 14


class _PpcBase(Measure):
    data_driven = True  # opened from a delivery episode, not demographics
    accepts_self_report = True  # the member can still confirm the visit

    def is_eligible(self, subject: Demographic, as_of: date) -> bool:
        # Real eligibility is "had a live-birth delivery" (episode-driven, handled
        # in ppc_service). This demographic screen — a female of a plausible
        # child-bearing age — is here for interface completeness only, since the
        # gap-opening pass skips data_driven measures.
        if subject.sex != "F":
            return False
        age = age_in_years(subject.date_of_birth, as_of)
        return age is not None and 10 <= age <= 64


class PrenatalCareMeasure(_PpcBase):
    code = "ppc_prenatal"
    hedis_measure_name = "Prenatal and Postpartum Care: Timeliness of Prenatal Care (PPC-Pre)"
    description = (
        "Confirms a timely prenatal visit (first trimester / within 42 days of enrollment) for a "
        "member's pregnancy episode. Most actionable when the pregnancy is known during it."
    )
    outreach_template = "prenatal_reminder"

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        had_visit = bool(payload["had_prenatal_visit"])
        return {
            "numerator_met": had_visit,
            "safety_flag": False,
            "needs_follow_up": False,  # a past prenatal window can't be rescheduled
            "instrument_scores": {"ppc_prenatal": {"had_prenatal_visit": had_visit}},
        }

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        return None


class PostpartumCareMeasure(_PpcBase):
    code = "ppc_postpartum"
    hedis_measure_name = "Prenatal and Postpartum Care: Postpartum Care (PPC-Post)"
    description = (
        "Confirms a postpartum visit 7–84 days after delivery, with scheduling assistance offered "
        "when one hasn't happened yet. The prospectively actionable half of PPC."
    )
    outreach_template = "postpartum_reminder"

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        had_visit = bool(payload["had_postpartum_visit"])
        wants_scheduling_help = bool(payload.get("wants_scheduling_help", False))
        return {
            "numerator_met": had_visit,
            "safety_flag": False,
            "needs_follow_up": (not had_visit) and wants_scheduling_help,
            "instrument_scores": {
                "ppc_postpartum": {
                    "had_postpartum_visit": had_visit,
                    "wants_scheduling_help": wants_scheduling_help,
                }
            },
        }

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        return POSTPARTUM_SCHEDULING_WINDOW_DAYS if evaluation.get("needs_follow_up") else None


prenatal_care_measure = PrenatalCareMeasure()
postpartum_care_measure = PostpartumCareMeasure()

PPC_MEASURES = [prenatal_care_measure, postpartum_care_measure]
