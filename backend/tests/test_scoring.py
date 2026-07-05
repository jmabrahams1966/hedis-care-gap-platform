import pytest

from app.scoring import score_gad7, score_phq9


def phq9(*, item9=0, fill=0):
    answers = [fill] * 9
    answers[8] = item9
    return answers


def test_phq9_severity_bands_at_exact_cutoffs():
    # total is sum of 9 answers 0-3; construct exact totals via first N items at 1, rest 0
    def with_total(total: int) -> list[int]:
        answers = [0] * 9
        remaining = total
        for i in range(9):
            take = min(3, remaining)
            answers[i] = take
            remaining -= take
        assert remaining == 0, "test helper cannot represent this total with 9 items of 0-3"
        return answers

    assert score_phq9(with_total(0))["severity"] == "minimal"
    assert score_phq9(with_total(4))["severity"] == "minimal"
    assert score_phq9(with_total(5))["severity"] == "mild"
    assert score_phq9(with_total(9))["severity"] == "mild"
    assert score_phq9(with_total(10))["severity"] == "moderate"
    assert score_phq9(with_total(14))["severity"] == "moderate"
    assert score_phq9(with_total(15))["severity"] == "moderately_severe"
    assert score_phq9(with_total(19))["severity"] == "moderately_severe"
    assert score_phq9(with_total(20))["severity"] == "severe"
    assert score_phq9(with_total(27))["severity"] == "severe"


def test_phq9_safety_flag_only_on_item9():
    assert score_phq9(phq9(item9=0))["safety_flag"] is False
    assert score_phq9(phq9(item9=1))["safety_flag"] is True
    assert score_phq9(phq9(item9=3))["safety_flag"] is True


def test_phq9_rejects_wrong_length():
    with pytest.raises(ValueError):
        score_phq9([0] * 8)
    with pytest.raises(ValueError):
        score_phq9([0] * 10)


def test_phq9_rejects_out_of_range_answer():
    with pytest.raises(ValueError):
        score_phq9([0, 0, 0, 0, 0, 0, 0, 0, 4])
    with pytest.raises(ValueError):
        score_phq9([0, 0, 0, 0, 0, 0, 0, 0, -1])


def test_gad7_severity_bands_at_exact_cutoffs():
    def with_total(total: int) -> list[int]:
        answers = [0] * 7
        remaining = total
        for i in range(7):
            take = min(3, remaining)
            answers[i] = take
            remaining -= take
        assert remaining == 0
        return answers

    assert score_gad7(with_total(0))["severity"] == "minimal"
    assert score_gad7(with_total(4))["severity"] == "minimal"
    assert score_gad7(with_total(5))["severity"] == "mild"
    assert score_gad7(with_total(9))["severity"] == "mild"
    assert score_gad7(with_total(10))["severity"] == "moderate"
    assert score_gad7(with_total(14))["severity"] == "moderate"
    assert score_gad7(with_total(15))["severity"] == "severe"
    assert score_gad7(with_total(21))["severity"] == "severe"


def test_gad7_rejects_wrong_length():
    with pytest.raises(ValueError):
        score_gad7([0] * 6)
