from .base import Measure
from .breast_cancer import breast_cancer_measure
from .mental_health import mental_health_measure

REGISTRY: dict[str, Measure] = {
    mental_health_measure.code: mental_health_measure,
    breast_cancer_measure.code: breast_cancer_measure,
}


def get_measure(code: str) -> Measure:
    try:
        return REGISTRY[code]
    except KeyError:
        raise ValueError(f"Unknown measure code: {code}")
