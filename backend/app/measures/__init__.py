from .base import Measure
from .blood_pressure import blood_pressure_measure
from .breast_cancer import breast_cancer_measure
from .childhood_immunization import childhood_immunization_measure
from .colorectal_cancer import colorectal_cancer_measure
from .diabetes import diabetes_a1c_measure
from .mental_health import mental_health_measure
from .well_child_visits import well_child_visits_measure

REGISTRY: dict[str, Measure] = {
    mental_health_measure.code: mental_health_measure,
    breast_cancer_measure.code: breast_cancer_measure,
    colorectal_cancer_measure.code: colorectal_cancer_measure,
    blood_pressure_measure.code: blood_pressure_measure,
    diabetes_a1c_measure.code: diabetes_a1c_measure,
    childhood_immunization_measure.code: childhood_immunization_measure,
    well_child_visits_measure.code: well_child_visits_measure,
}


def get_measure(code: str) -> Measure:
    try:
        return REGISTRY[code]
    except KeyError:
        raise ValueError(f"Unknown measure code: {code}")
