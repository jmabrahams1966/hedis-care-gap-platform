from datetime import date

import pytest

from app.measures.breast_cancer import breast_cancer_measure
from app.measures.mental_health import mental_health_measure
from app.models import Member

TODAY = date(2026, 7, 5)


def make_member(dob: str, sex: str = "U") -> Member:
    return Member(
        tenant_id="t1",
        external_member_id="ext",
        first_name="Test",
        last_name="Member",
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
