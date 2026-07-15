from datetime import date

import pytest

from app.measures.medication_adherence import (
    pdc_diabetes_measure,
    pdc_hypertension_measure,
    pdc_statins_measure,
)
from app.measures.pdc import Fill, compute_pdc

YEAR_START = date(2026, 1, 1)
YEAR_END = date(2026, 12, 31)


# --- PDC calculation (pure) ---


def test_pdc_single_fill_not_eligible():
    result = compute_pdc([Fill(date(2026, 1, 1), 90)], YEAR_START, YEAR_END)
    assert result.eligible is False
    assert result.pdc is None
    assert result.adherent is False


def test_pdc_two_fills_same_day_not_eligible():
    # Eligibility is >= 2 fills on *distinct* dates, not two on the same day.
    fills = [Fill(date(2026, 1, 1), 30), Fill(date(2026, 1, 1), 30)]
    result = compute_pdc(fills, YEAR_START, YEAR_END)
    assert result.eligible is False


def test_pdc_continuous_monthly_fills_is_adherent():
    # 30-day fills on the 1st of each month → essentially continuous coverage.
    fills = [Fill(date(2026, m, 1), 31) for m in range(1, 13)]
    result = compute_pdc(fills, YEAR_START, YEAR_END)
    assert result.eligible is True
    assert result.adherent is True
    assert result.pdc >= 0.80
    assert result.covered_days <= result.treatment_days  # never over-count


def test_pdc_sparse_fills_not_adherent():
    # Two 30-day fills in January, then nothing for the rest of the year.
    fills = [Fill(date(2026, 1, 1), 30), Fill(date(2026, 2, 1), 30)]
    result = compute_pdc(fills, YEAR_START, YEAR_END)
    assert result.eligible is True
    assert result.adherent is False
    assert result.pdc < 0.80


def test_pdc_treatment_period_starts_at_first_fill_not_jan_1():
    # First fill July 1; treatment period is Jul 1..Dec 31 (184 days), fully
    # covered by back-to-back 31-day fills → adherent, not diluted by H1 absence.
    fills = [Fill(date(2026, m, 1), 31) for m in range(7, 13)]
    result = compute_pdc(fills, YEAR_START, YEAR_END)
    assert result.ipsd == date(2026, 7, 1)
    assert result.treatment_days == (YEAR_END - date(2026, 7, 1)).days + 1
    assert result.adherent is True


def test_pdc_early_refills_do_not_exceed_one():
    # Heavy stockpiling: a 90-day fill every 30 days. Coverage can't exceed the
    # treatment period, so PDC stays capped at 1.0.
    fills = [Fill(date(2026, 1, 1), 90), Fill(date(2026, 1, 31), 90), Fill(date(2026, 3, 1), 90)]
    result = compute_pdc(fills, YEAR_START, YEAR_END)
    assert result.pdc <= 1.0
    assert result.covered_days <= result.treatment_days


def test_pdc_coverage_clipped_at_period_end():
    # A 200-day fill starting Nov 1 only counts the days through Dec 31.
    fills = [Fill(date(2026, 11, 1), 200), Fill(date(2026, 11, 15), 30)]
    result = compute_pdc(fills, YEAR_START, YEAR_END)
    assert result.covered_days == (YEAR_END - date(2026, 11, 1)).days + 1


def test_pdc_ignores_fills_outside_period():
    fills = [Fill(date(2025, 12, 1), 30), Fill(date(2026, 1, 1), 30), Fill(date(2026, 2, 1), 30)]
    result = compute_pdc(fills, YEAR_START, YEAR_END)
    # Only the two 2026 fills count toward eligibility; the 2025 fill is ignored.
    assert result.distinct_fill_dates == 2
    assert result.ipsd == date(2026, 1, 1)


# --- Measure metadata / interface ---


@pytest.mark.parametrize(
    "measure,drug_class",
    [
        (pdc_diabetes_measure, "diabetes"),
        (pdc_hypertension_measure, "rasa"),
        (pdc_statins_measure, "statins"),
    ],
)
def test_pdc_measures_are_data_driven(measure, drug_class):
    assert measure.data_driven is True
    assert measure.drug_class == drug_class
    assert measure.subject_type == "member"


def test_pdc_measure_age_gate_18_plus():
    class Subj:
        def __init__(self, dob):
            self.date_of_birth = dob
            self.sex = "U"

    today = date(2026, 7, 5)
    assert pdc_diabetes_measure.is_eligible(Subj("1980-01-01"), today) is True
    assert pdc_diabetes_measure.is_eligible(Subj(f"{today.year - 17}-01-01"), today) is False


def test_pdc_evaluate_submission_rejected():
    # PDC has no member self-report entry point.
    with pytest.raises(ValueError):
        pdc_diabetes_measure.evaluate_submission({"anything": True})


def test_pdc_no_follow_up_window():
    assert pdc_diabetes_measure.follow_up_window_days({}) is None
