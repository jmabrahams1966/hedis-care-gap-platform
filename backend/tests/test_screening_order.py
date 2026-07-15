from app.routers.screenings import _screening_priority, _SCREENING_PRIORITY


def test_priority_orders_maternity_before_screenings_before_pediatric():
    order = sorted(
        ["well_child_visits", "mental_health", "ppc_postpartum", "cervical_cancer", "blood_pressure"],
        key=_screening_priority,
    )
    assert order == ["ppc_postpartum", "blood_pressure", "mental_health", "cervical_cancer", "well_child_visits"]


def test_unknown_measure_sorts_last():
    assert _screening_priority("something_new") == len(_SCREENING_PRIORITY)
    assert _screening_priority("ppc_postpartum") == 0
