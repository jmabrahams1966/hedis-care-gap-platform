from datetime import date

import pytest

from app.measures.blood_pressure import blood_pressure_measure
from app.measures.breast_cancer import breast_cancer_measure
from app.measures.cervical_cancer import cervical_cancer_measure
from app.measures.childhood_immunization import childhood_immunization_measure
from app.measures.colorectal_cancer import colorectal_cancer_measure
from app.measures.diabetes import diabetes_a1c_measure
from app.measures.eye_exam import eye_exam_measure
from app.measures.kidney_health import kidney_health_measure
from app.measures.mental_health import mental_health_measure
from app.measures.well_child_visits import well_child_visits_measure
from app.models import Dependent, Member

TODAY = date(2026, 7, 5)


def make_member(dob: str, sex: str = "U", conditions: list[str] | None = None) -> Member:
    return Member(
        tenant_id="t1",
        external_member_id="ext",
        first_name="Test",
        last_name="Member",
        date_of_birth=dob,
        sex=sex,
        conditions=conditions or [],
    )


def make_dependent(dob: str, sex: str = "U") -> Dependent:
    return Dependent(
        tenant_id="t1",
        guardian_member_id="m1",
        external_dependent_id="ext-dep",
        first_name="Kid",
        last_name="Test",
        date_of_birth=dob,
        sex=sex,
    )


# --- Mental health (DSF) ---


def test_mental_health_eligible_at_12_not_below():
    just_turned_12 = Member(
        tenant_id="t1", external_member_id="e", first_name="A", last_name="B",
        date_of_birth=f"{TODAY.year - 12}-{TODAY.month:02d}-{TODAY.day:02d}",
    )
    assert mental_health_measure.is_eligible(just_turned_12, TODAY) is True

    almost_12 = Member(
        tenant_id="t1", external_member_id="e", first_name="A", last_name="B",
        date_of_birth=f"{TODAY.year - 12}-{TODAY.month:02d}-{min(TODAY.day + 1, 28):02d}",
    )
    assert mental_health_measure.is_eligible(almost_12, TODAY) is False


def test_mental_health_no_sex_restriction():
    adult = make_member("1980-01-01", sex="U")
    assert mental_health_measure.is_eligible(adult, TODAY) is True


def test_mental_health_evaluate_minimal_score_no_follow_up():
    evaluation = mental_health_measure.evaluate_submission({"phq9": [0] * 9, "gad7": [0] * 7})
    assert evaluation["numerator_met"] is True
    assert evaluation["safety_flag"] is False
    assert evaluation["needs_follow_up"] is False
    assert mental_health_measure.follow_up_window_days(evaluation) is None


def test_mental_health_evaluate_moderate_score_opens_30_day_follow_up():
    # total 10 -> moderate
    answers = [2, 2, 2, 2, 2, 0, 0, 0, 0]
    evaluation = mental_health_measure.evaluate_submission({"phq9": answers, "gad7": None})
    assert evaluation["numerator_met"] is True
    assert evaluation["needs_follow_up"] is True
    assert evaluation["safety_flag"] is False
    assert mental_health_measure.follow_up_window_days(evaluation) == 30


def test_mental_health_safety_flag_forces_1_day_follow_up_even_if_mild():
    # low total but item 9 positive
    answers = [0, 0, 0, 0, 0, 0, 0, 0, 1]
    evaluation = mental_health_measure.evaluate_submission({"phq9": answers, "gad7": None})
    assert evaluation["safety_flag"] is True
    assert evaluation["needs_follow_up"] is True
    assert mental_health_measure.follow_up_window_days(evaluation) == 1


def test_mental_health_missing_phq9_raises():
    with pytest.raises(KeyError):
        mental_health_measure.evaluate_submission({})


# --- Breast cancer screening (BCS) ---


@pytest.mark.parametrize("age,expected", [(49, False), (50, True), (74, True), (75, False)])
def test_bcs_age_band(age, expected):
    dob = f"{TODAY.year - age}-{TODAY.month:02d}-{TODAY.day:02d}"
    member = make_member(dob, sex="F")
    assert breast_cancer_measure.is_eligible(member, TODAY) is expected


def test_bcs_requires_female():
    member = make_member("1970-01-01", sex="M")
    assert breast_cancer_measure.is_eligible(member, TODAY) is False
    member_u = make_member("1970-01-01", sex="U")
    assert breast_cancer_measure.is_eligible(member_u, TODAY) is False


def test_bcs_completed_meets_numerator_no_follow_up():
    evaluation = breast_cancer_measure.evaluate_submission({"has_completed": True})
    assert evaluation["numerator_met"] is True
    assert evaluation["needs_follow_up"] is False
    assert breast_cancer_measure.follow_up_window_days(evaluation) is None


def test_bcs_not_completed_wants_help_opens_14_day_follow_up():
    evaluation = breast_cancer_measure.evaluate_submission(
        {"has_completed": False, "wants_scheduling_help": True}
    )
    assert evaluation["numerator_met"] is False
    assert evaluation["needs_follow_up"] is True
    assert breast_cancer_measure.follow_up_window_days(evaluation) == 14


def test_bcs_not_completed_declines_help_stays_open_no_follow_up_window():
    evaluation = breast_cancer_measure.evaluate_submission(
        {"has_completed": False, "wants_scheduling_help": False}
    )
    assert evaluation["numerator_met"] is False
    assert evaluation["needs_follow_up"] is False
    assert breast_cancer_measure.follow_up_window_days(evaluation) is None


def test_bcs_missing_has_completed_raises():
    with pytest.raises(KeyError):
        breast_cancer_measure.evaluate_submission({})


# --- Cervical cancer screening (CCS) ---


@pytest.mark.parametrize("age,expected", [(20, False), (21, True), (64, True), (65, False)])
def test_ccs_age_band(age, expected):
    dob = f"{TODAY.year - age}-{TODAY.month:02d}-{TODAY.day:02d}"
    assert cervical_cancer_measure.is_eligible(make_member(dob, sex="F"), TODAY) is expected


def test_ccs_requires_female():
    assert cervical_cancer_measure.is_eligible(make_member("1985-01-01", sex="M"), TODAY) is False
    assert cervical_cancer_measure.is_eligible(make_member("1985-01-01", sex="U"), TODAY) is False


def test_ccs_completed_meets_numerator_no_follow_up():
    evaluation = cervical_cancer_measure.evaluate_submission({"has_completed": True})
    assert evaluation["numerator_met"] is True
    assert evaluation["needs_follow_up"] is False
    assert cervical_cancer_measure.follow_up_window_days(evaluation) is None


def test_ccs_not_completed_wants_help_opens_14_day_follow_up():
    evaluation = cervical_cancer_measure.evaluate_submission({"has_completed": False, "wants_scheduling_help": True})
    assert evaluation["numerator_met"] is False
    assert evaluation["needs_follow_up"] is True
    assert cervical_cancer_measure.follow_up_window_days(evaluation) == 14


def test_ccs_missing_has_completed_raises():
    with pytest.raises(KeyError):
        cervical_cancer_measure.evaluate_submission({})


# --- Colorectal cancer screening (COL) ---


@pytest.mark.parametrize("age,expected", [(44, False), (45, True), (75, True), (76, False)])
def test_col_age_band(age, expected):
    dob = f"{TODAY.year - age}-{TODAY.month:02d}-{TODAY.day:02d}"
    assert colorectal_cancer_measure.is_eligible(make_member(dob, sex="F"), TODAY) is expected
    # no sex restriction — same age band applies regardless of sex
    assert colorectal_cancer_measure.is_eligible(make_member(dob, sex="M"), TODAY) is expected


def test_col_completed_meets_numerator():
    evaluation = colorectal_cancer_measure.evaluate_submission({"has_completed": True, "screening_type": "fit"})
    assert evaluation["numerator_met"] is True
    assert evaluation["needs_follow_up"] is False


def test_col_not_completed_wants_help():
    evaluation = colorectal_cancer_measure.evaluate_submission(
        {"has_completed": False, "wants_scheduling_help": True}
    )
    assert evaluation["needs_follow_up"] is True
    assert colorectal_cancer_measure.follow_up_window_days(evaluation) == 14


# --- Controlling high blood pressure (CBP) ---


def test_bp_requires_hypertension_condition():
    with_condition = make_member("1970-01-01", conditions=["hypertension"])
    without_condition = make_member("1970-01-01", conditions=[])
    assert blood_pressure_measure.is_eligible(with_condition, TODAY) is True
    assert blood_pressure_measure.is_eligible(without_condition, TODAY) is False


@pytest.mark.parametrize("age,expected", [(17, False), (18, True), (85, True), (86, False)])
def test_bp_age_band(age, expected):
    dob = f"{TODAY.year - age}-{TODAY.month:02d}-{TODAY.day:02d}"
    member = make_member(dob, conditions=["hypertension"])
    assert blood_pressure_measure.is_eligible(member, TODAY) is expected


def test_bp_controlled_reading_meets_numerator():
    evaluation = blood_pressure_measure.evaluate_submission({"systolic": 128, "diastolic": 78})
    assert evaluation["numerator_met"] is True
    assert evaluation["safety_flag"] is False
    assert evaluation["needs_follow_up"] is False
    assert blood_pressure_measure.follow_up_window_days(evaluation) is None


def test_bp_above_goal_opens_14_day_follow_up_no_safety_flag():
    evaluation = blood_pressure_measure.evaluate_submission({"systolic": 148, "diastolic": 92})
    assert evaluation["numerator_met"] is False
    assert evaluation["safety_flag"] is False
    assert evaluation["needs_follow_up"] is True
    assert blood_pressure_measure.follow_up_window_days(evaluation) == 14


@pytest.mark.parametrize("systolic,diastolic", [(185, 100), (150, 125), (190, 130)])
def test_bp_crisis_range_sets_safety_flag_and_1_day_follow_up(systolic, diastolic):
    evaluation = blood_pressure_measure.evaluate_submission({"systolic": systolic, "diastolic": diastolic})
    assert evaluation["safety_flag"] is True
    assert blood_pressure_measure.follow_up_window_days(evaluation) == 1


def test_bp_rejects_implausible_reading():
    with pytest.raises(ValueError):
        blood_pressure_measure.evaluate_submission({"systolic": 500, "diastolic": 90})
    with pytest.raises(ValueError):
        blood_pressure_measure.evaluate_submission({"systolic": 120, "diastolic": 10})


# --- Diabetes HbA1c testing & control (CDC subset) ---


def test_a1c_requires_diabetes_condition():
    with_condition = make_member("1970-01-01", conditions=["diabetes"])
    without_condition = make_member("1970-01-01", conditions=[])
    assert diabetes_a1c_measure.is_eligible(with_condition, TODAY) is True
    assert diabetes_a1c_measure.is_eligible(without_condition, TODAY) is False


def test_a1c_tested_and_controlled_meets_numerator_no_follow_up():
    evaluation = diabetes_a1c_measure.evaluate_submission({"has_recent_test": True, "a1c_value": 6.8})
    assert evaluation["numerator_met"] is True
    assert evaluation["needs_follow_up"] is False
    assert diabetes_a1c_measure.follow_up_window_days(evaluation) is None


def test_a1c_tested_but_poor_control_opens_follow_up():
    evaluation = diabetes_a1c_measure.evaluate_submission({"has_recent_test": True, "a1c_value": 9.8})
    assert evaluation["numerator_met"] is True  # numerator is "tested", independent of control
    assert evaluation["needs_follow_up"] is True
    assert diabetes_a1c_measure.follow_up_window_days(evaluation) == 30


def test_a1c_not_tested_opens_follow_up():
    evaluation = diabetes_a1c_measure.evaluate_submission({"has_recent_test": False})
    assert evaluation["numerator_met"] is False
    assert evaluation["needs_follow_up"] is True


def test_a1c_missing_value_treated_as_untested_control_unknown():
    evaluation = diabetes_a1c_measure.evaluate_submission({"has_recent_test": True, "a1c_value": None})
    assert evaluation["numerator_met"] is True
    assert evaluation["needs_follow_up"] is False  # can't flag poor control without a value


# --- Eye Exam for Patients with Diabetes (EED) — diabetes bundle ---


def test_eed_requires_diabetes_condition():
    assert eye_exam_measure.is_eligible(make_member("1970-01-01", conditions=["diabetes"]), TODAY) is True
    assert eye_exam_measure.is_eligible(make_member("1970-01-01", conditions=[]), TODAY) is False


@pytest.mark.parametrize("age,expected", [(17, False), (18, True), (75, True), (76, False)])
def test_eed_age_band(age, expected):
    dob = f"{TODAY.year - age}-{TODAY.month:02d}-{TODAY.day:02d}"
    assert eye_exam_measure.is_eligible(make_member(dob, conditions=["diabetes"]), TODAY) is expected


def test_eed_completed_meets_numerator_no_follow_up():
    evaluation = eye_exam_measure.evaluate_submission({"has_completed": True})
    assert evaluation["numerator_met"] is True
    assert evaluation["needs_follow_up"] is False
    assert eye_exam_measure.follow_up_window_days(evaluation) is None


def test_eed_not_completed_wants_help_opens_14_day_follow_up():
    evaluation = eye_exam_measure.evaluate_submission({"has_completed": False, "wants_scheduling_help": True})
    assert evaluation["numerator_met"] is False
    assert evaluation["needs_follow_up"] is True
    assert eye_exam_measure.follow_up_window_days(evaluation) == 14


def test_eed_missing_has_completed_raises():
    with pytest.raises(KeyError):
        eye_exam_measure.evaluate_submission({})


# --- Kidney Health Evaluation for Patients with Diabetes (KED) — needs BOTH tests ---


def test_ked_requires_diabetes_condition():
    assert kidney_health_measure.is_eligible(make_member("1970-01-01", conditions=["diabetes"]), TODAY) is True
    assert kidney_health_measure.is_eligible(make_member("1970-01-01", conditions=[]), TODAY) is False


@pytest.mark.parametrize("age,expected", [(17, False), (18, True), (85, True), (86, False)])
def test_ked_age_band(age, expected):
    dob = f"{TODAY.year - age}-{TODAY.month:02d}-{TODAY.day:02d}"
    assert kidney_health_measure.is_eligible(make_member(dob, conditions=["diabetes"]), TODAY) is expected


def test_ked_both_tests_meet_numerator():
    evaluation = kidney_health_measure.evaluate_submission({"has_egfr": True, "has_uacr": True})
    assert evaluation["numerator_met"] is True
    assert evaluation["needs_follow_up"] is False
    assert kidney_health_measure.follow_up_window_days(evaluation) is None


@pytest.mark.parametrize("egfr,uacr", [(True, False), (False, True), (False, False)])
def test_ked_one_or_neither_test_does_not_meet_numerator(egfr, uacr):
    evaluation = kidney_health_measure.evaluate_submission({"has_egfr": egfr, "has_uacr": uacr})
    assert evaluation["numerator_met"] is False


def test_ked_incomplete_wants_help_opens_14_day_follow_up():
    evaluation = kidney_health_measure.evaluate_submission(
        {"has_egfr": True, "has_uacr": False, "wants_scheduling_help": True}
    )
    assert evaluation["needs_follow_up"] is True
    assert kidney_health_measure.follow_up_window_days(evaluation) == 14


def test_ked_missing_a_test_key_raises():
    with pytest.raises(KeyError):
        kidney_health_measure.evaluate_submission({"has_egfr": True})


# --- Childhood Immunization Status (CIS) — first dependent-scoped measure ---


def test_cis_is_dependent_scoped():
    assert childhood_immunization_measure.subject_type == "dependent"


@pytest.mark.parametrize("age,expected", [(1, False), (2, True), (3, False)])
def test_cis_eligible_only_at_age_2(age, expected):
    dob = f"{TODAY.year - age}-{TODAY.month:02d}-{TODAY.day:02d}"
    assert childhood_immunization_measure.is_eligible(make_dependent(dob), TODAY) is expected


def test_cis_completed_meets_numerator():
    evaluation = childhood_immunization_measure.evaluate_submission({"has_completed": True})
    assert evaluation["numerator_met"] is True
    assert evaluation["needs_follow_up"] is False


def test_cis_not_completed_wants_help_opens_14_day_follow_up():
    evaluation = childhood_immunization_measure.evaluate_submission(
        {"has_completed": False, "wants_scheduling_help": True}
    )
    assert evaluation["needs_follow_up"] is True
    assert childhood_immunization_measure.follow_up_window_days(evaluation) == 14


# --- Well-Child Visits (WCV) ---


def test_wcv_is_dependent_scoped():
    assert well_child_visits_measure.subject_type == "dependent"


@pytest.mark.parametrize("age,expected", [(2, False), (3, True), (17, True), (18, False)])
def test_wcv_age_band(age, expected):
    dob = f"{TODAY.year - age}-{TODAY.month:02d}-{TODAY.day:02d}"
    assert well_child_visits_measure.is_eligible(make_dependent(dob), TODAY) is expected


def test_wcv_completed_meets_numerator():
    evaluation = well_child_visits_measure.evaluate_submission({"has_completed": True})
    assert evaluation["numerator_met"] is True
    assert evaluation["needs_follow_up"] is False


def test_wcv_not_completed_declines_help_stays_open():
    evaluation = well_child_visits_measure.evaluate_submission(
        {"has_completed": False, "wants_scheduling_help": False}
    )
    assert evaluation["numerator_met"] is False
    assert evaluation["needs_follow_up"] is False
    assert well_child_visits_measure.follow_up_window_days(evaluation) is None
