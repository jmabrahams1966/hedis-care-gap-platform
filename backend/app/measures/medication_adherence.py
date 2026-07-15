"""Medication adherence (PDC) measures — the three triple-weighted Part D Star
measures: diabetes medications, RAS-antagonist antihypertensives, and statins.

These are the first `data_driven` measures: unlike every screening measure, the
numerator isn't a member self-report — it's the Proportion of Days Covered
computed from ingested pharmacy fills (see app/measures/pdc.py and
app/measures/pdc_service.py). `evaluate_submission` therefore has no meaning
here and is rejected; gaps are opened when fills arrive, not by the demographic
gap-opening pass.
"""

from datetime import date
from typing import Any

from .base import Demographic, Measure, age_in_years


class MedicationAdherenceMeasure(Measure):
    data_driven = True
    accepts_self_report = False  # numerator is computed from fills, no member form
    outreach_template = "refill_reminder"

    def __init__(self, *, code: str, hedis_measure_name: str, drug_class: str, description: str) -> None:
        self.code = code
        self.hedis_measure_name = hedis_measure_name
        self.drug_class = drug_class
        self.description = description

    def is_eligible(self, subject: Demographic, as_of: date) -> bool:
        """Coarse age gate only (18+). The real denominator — a member dispensed
        the drug class at least twice — is fills-based and can't be seen by this
        pure-demographic hook, so it's evaluated in pdc_service when fills are
        ingested. `_open_care_gaps_for_member` skips data-driven measures, so
        this isn't used to open gaps; it's here for interface completeness and
        for callers that want the age screen."""
        age = age_in_years(subject.date_of_birth, as_of)
        return age is not None and age >= 18

    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise ValueError(
            "Medication adherence (PDC) is computed from pharmacy fills, not a member "
            "self-report — ingest fills via /api/medications/fills instead."
        )

    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        return None


pdc_diabetes_measure = MedicationAdherenceMeasure(
    code="pdc_diabetes",
    hedis_measure_name="Medication Adherence for Diabetes Medications (PDC-DR)",
    drug_class="diabetes",
    description=(
        "Proportion of Days Covered (PDC) ≥ 80% for non-insulin diabetes medications, "
        "computed from pharmacy fills; drives refill-reminder outreach to members trending non-adherent."
    ),
)

pdc_hypertension_measure = MedicationAdherenceMeasure(
    code="pdc_hypertension",
    hedis_measure_name="Medication Adherence for Hypertension / RAS Antagonists (PDC-RASA)",
    drug_class="rasa",
    description=(
        "PDC ≥ 80% for RAS-antagonist antihypertensives (ACEIs, ARBs, direct renin inhibitors), "
        "computed from pharmacy fills."
    ),
)

pdc_statins_measure = MedicationAdherenceMeasure(
    code="pdc_statins",
    hedis_measure_name="Medication Adherence for Cholesterol / Statins (PDC-STA)",
    drug_class="statins",
    description="PDC ≥ 80% for statin cholesterol medications, computed from pharmacy fills.",
)

#: All medication-adherence measures, and a drug_class → measure lookup used by
#: the fills ingestion / recompute path.
MEDICATION_ADHERENCE_MEASURES = [
    pdc_diabetes_measure,
    pdc_hypertension_measure,
    pdc_statins_measure,
]
MEASURE_BY_DRUG_CLASS = {m.drug_class: m for m in MEDICATION_ADHERENCE_MEASURES}
