"""Proportion of Days Covered (PDC) — the calculation behind the HEDIS/Part D
medication-adherence measures (PDC-Diabetes, PDC-RASA/hypertension, PDC-Statins).

Pure functions, no DB. Given a member's pharmacy fills for one drug class,
compute what fraction of the treatment period they had medication on hand.
A member is "adherent" at PDC >= 0.80.

Two things worth calling out versus the letter of the NCQA spec:

1. **In-year (run-to-date) PDC.** The HEDIS measure is scored over the full
   calendar measurement year. This platform is an *operational* tool — the
   point is to nudge a member back on track *before* year-end — so the
   treatment period ends at the run date (`as_of`), not December 31. That makes
   the number reflect adherence *so far*; at year-end (as_of >= Dec 31) it
   converges to the HEDIS full-year value. Callers pass `period_end` already
   clamped to the run date.
2. **Early-refill carry-over.** When a member refills before their prior supply
   runs out, the extra days stack forward (stockpiling) rather than being lost
   — the standard PDC handling. Coverage is still capped at the treatment
   period, so PDC never exceeds 1.0.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

#: A member is adherent when at least 80% of the treatment period is covered.
ADHERENCE_THRESHOLD = 0.80


@dataclass(frozen=True)
class Fill:
    """One pharmacy dispensing event for a single drug class."""

    fill_date: date
    days_supply: int


@dataclass(frozen=True)
class PdcResult:
    eligible: bool  # >= 2 fills on distinct dates in the period → in the PDC denominator
    pdc: float | None  # proportion covered (0..1), None when not eligible
    adherent: bool  # pdc >= ADHERENCE_THRESHOLD
    covered_days: int
    treatment_days: int
    fill_count: int
    distinct_fill_dates: int
    ipsd: date | None  # index prescription start date (first fill in the period)


def parse_fill_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def compute_pdc(fills: list[Fill], period_start: date, period_end: date) -> PdcResult:
    """Compute PDC for one drug class over [period_start, period_end].

    Denominator eligibility is >= 2 fills on distinct dates within the period
    (a member dispensed the drug only once was never really "on therapy" for
    adherence purposes). The treatment period runs from the first such fill
    (IPSD) to period_end.
    """
    in_period = [f for f in fills if period_start <= f.fill_date <= period_end and f.days_supply > 0]
    distinct_dates = {f.fill_date for f in in_period}
    if len(distinct_dates) < 2:
        return PdcResult(
            eligible=False,
            pdc=None,
            adherent=False,
            covered_days=0,
            treatment_days=0,
            fill_count=len(in_period),
            distinct_fill_dates=len(distinct_dates),
            ipsd=None,
        )

    ipsd = min(distinct_dates)
    end_exclusive = period_end + timedelta(days=1)
    treatment_days = (period_end - ipsd).days + 1

    # Walk fills in date order, carrying coverage forward. `covered_through` is
    # the exclusive day up to which the member already has supply; an early
    # refill starts stacking from there (stockpiling) rather than its fill date,
    # while a late refill after a gap starts fresh at its own fill date.
    covered_days = 0
    covered_through = ipsd
    for fill in sorted(in_period, key=lambda f: f.fill_date):
        start = max(fill.fill_date, covered_through)
        if start >= end_exclusive:
            continue
        stop = min(start + timedelta(days=fill.days_supply), end_exclusive)
        if stop > start:
            covered_days += (stop - start).days
            covered_through = stop

    pdc = covered_days / treatment_days if treatment_days > 0 else 0.0
    return PdcResult(
        eligible=True,
        pdc=round(pdc, 4),
        adherent=pdc >= ADHERENCE_THRESHOLD,
        covered_days=covered_days,
        treatment_days=treatment_days,
        fill_count=len(in_period),
        distinct_fill_dates=len(distinct_dates),
        ipsd=ipsd,
    )
