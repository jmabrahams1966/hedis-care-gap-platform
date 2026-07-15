from .base import Measure
from .blood_pressure import blood_pressure_measure
from .breast_cancer import breast_cancer_measure
from .cervical_cancer import cervical_cancer_measure
from .childhood_immunization import childhood_immunization_measure
from .colorectal_cancer import colorectal_cancer_measure
from .diabetes import diabetes_a1c_measure
from .eye_exam import eye_exam_measure
from .kidney_health import kidney_health_measure
from .medication_adherence import (
    pdc_diabetes_measure,
    pdc_hypertension_measure,
    pdc_statins_measure,
)
from .mental_health import mental_health_measure
from .prenatal_postpartum import postpartum_care_measure, prenatal_care_measure
from .well_child_visits import well_child_visits_measure

REGISTRY: dict[str, Measure] = {
    mental_health_measure.code: mental_health_measure,
    breast_cancer_measure.code: breast_cancer_measure,
    cervical_cancer_measure.code: cervical_cancer_measure,
    colorectal_cancer_measure.code: colorectal_cancer_measure,
    blood_pressure_measure.code: blood_pressure_measure,
    diabetes_a1c_measure.code: diabetes_a1c_measure,
    eye_exam_measure.code: eye_exam_measure,
    kidney_health_measure.code: kidney_health_measure,
    childhood_immunization_measure.code: childhood_immunization_measure,
    well_child_visits_measure.code: well_child_visits_measure,
    pdc_diabetes_measure.code: pdc_diabetes_measure,
    pdc_hypertension_measure.code: pdc_hypertension_measure,
    pdc_statins_measure.code: pdc_statins_measure,
    prenatal_care_measure.code: prenatal_care_measure,
    postpartum_care_measure.code: postpartum_care_measure,
}


def get_measure(code: str) -> Measure:
    try:
        return REGISTRY[code]
    except KeyError:
        raise ValueError(f"Unknown measure code: {code}")
