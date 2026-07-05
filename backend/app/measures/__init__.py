from .base import Measure
from .mental_health import mental_health_measure

REGISTRY: dict[str, Measure] = {
    mental_health_measure.code: mental_health_measure,
}


def get_measure(code: str) -> Measure:
    try:
        return REGISTRY[code]
    except KeyError:
        raise ValueError(f"Unknown measure code: {code}")
