"""Recompute PDC medication-adherence care gaps for a member from their
pharmacy fills. Called after fills are ingested (app/routers/medications.py) and
reusable from the demo seed / a future scheduled reconciliation job.

This is the data-driven counterpart to `_open_care_gaps_for_member`: screening
measures open a gap for every demographically-eligible member up front, but a
PDC gap only exists once the fills prove the member is on therapy (≥ 2 fills of
the class), so opening happens here, keyed off the claims data, not demographics.
"""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CareGap, GapStatus, Member, MedicationFill, NumeratorSource, TenantMeasureConfig
from .base import default_period
from .exclusions import is_excluded, member_exclusion_codes
from .medication_adherence import MEDICATION_ADHERENCE_MEASURES
from .pdc import Fill, PdcResult, compute_pdc, parse_fill_date

MEASURE_BY_CODE = {m.code: m for m in MEDICATION_ADHERENCE_MEASURES}


async def _enabled_pdc_codes(db: AsyncSession, tenant_id: str) -> set[str]:
    rows = (
        await db.execute(
            select(TenantMeasureConfig.measure_code).where(
                TenantMeasureConfig.tenant_id == tenant_id,
                TenantMeasureConfig.enabled.is_(True),
            )
        )
    ).scalars().all()
    pdc_codes = {m.code for m in MEDICATION_ADHERENCE_MEASURES}
    return set(rows) & pdc_codes


async def pdc_snapshot_for_member(
    db: AsyncSession, member: Member, *, as_of: date | None = None
) -> list[tuple[str, "PdcResult"]]:
    """Read-only: compute PDC per enabled measure from the member's fills without
    touching any care gap. Returns [(measure_code, PdcResult), ...]."""
    as_of = as_of or date.today()
    period_start = date(as_of.year, 1, 1)
    # Operational, run-to-date PDC: the treatment period ends at the run date,
    # never in the future (see app/measures/pdc.py). At year-end this is the
    # full HEDIS measurement year.
    period_end = min(date(as_of.year, 12, 31), as_of)

    enabled = await _enabled_pdc_codes(db, member.tenant_id)
    if not enabled:
        return []

    fills = (
        await db.execute(select(MedicationFill).where(MedicationFill.member_id == member.id))
    ).scalars().all()

    out: list[tuple[str, PdcResult]] = []
    for measure in MEDICATION_ADHERENCE_MEASURES:
        if measure.code not in enabled:
            continue
        class_fills = [
            Fill(fill_date=d, days_supply=f.days_supply)
            for f in fills
            if f.drug_class == measure.drug_class and (d := parse_fill_date(f.fill_date)) is not None
        ]
        out.append((measure.code, compute_pdc(class_fills, period_start, period_end)))
    return out


async def recompute_pdc_for_member(
    db: AsyncSession, member: Member, *, as_of: date | None = None
) -> list[dict]:
    """For each PDC measure enabled on the member's tenant, compute PDC from the
    member's fills and open/update the corresponding CareGap. Returns a summary
    per computed measure. Does not commit — the caller owns the transaction.
    """
    as_of = as_of or date.today()
    period = default_period(as_of)
    period_end = min(date(as_of.year, 12, 31), as_of)

    snapshot = await pdc_snapshot_for_member(db, member, as_of=as_of)
    exclusion_codes = await member_exclusion_codes(db, member.id)

    summaries: list[dict] = []
    for measure_code, result in snapshot:
        if is_excluded(exclusion_codes, MEASURE_BY_CODE[measure_code]):
            continue  # broad exclusion (hospice/deceased) — not in the denominator
        gap = (
            await db.execute(
                select(CareGap).where(
                    CareGap.member_id == member.id,
                    CareGap.dependent_id.is_(None),
                    CareGap.measure_code == measure_code,
                    CareGap.period == period,
                )
            )
        ).scalar_one_or_none()

        if not result.eligible:
            # Fewer than two fills of the class — the member isn't in the PDC
            # denominator (they were never on therapy). Don't fabricate a gap;
            # if one exists from earlier data we leave it untouched rather than
            # guess whether fills went missing.
            summaries.append(
                {"measure_code": measure_code, "eligible": False, "pdc": None, "adherent": False}
            )
            continue

        if gap is None:
            gap = CareGap(
                tenant_id=member.tenant_id,
                member_id=member.id,
                measure_code=measure_code,
                period=period,
            )
            db.add(gap)
            await db.flush()

        reference = (
            f"PDC {result.pdc:.0%} ({result.covered_days}/{result.treatment_days} days, "
            f"{result.fill_count} fills through {period_end.isoformat()})"
        )
        gap.numerator_met = result.adherent
        gap.numerator_source_reference = reference
        if result.adherent:
            # Claims-derived proof of a met numerator — the strongest provenance,
            # the same tier as a staff claims confirmation.
            gap.numerator_source = NumeratorSource.claims_confirmed.value
            gap.status = GapStatus.completed.value
            gap.closed_at = datetime.utcnow()
            gap.closure_reason = "pdc_adherent"
        else:
            # Below 0.80: numerator not met. Keep provenance `unconfirmed` (we've
            # confirmed non-adherence, not a met numerator) and keep the gap open
            # so the refill-reminder outreach cadence picks it up — unless staff
            # have already closed/excluded it or outreach is mid-flight.
            gap.numerator_source = NumeratorSource.unconfirmed.value
            if gap.status not in (
                GapStatus.closed.value,
                GapStatus.excluded.value,
                GapStatus.outreach_sent.value,
            ):
                gap.status = GapStatus.open.value
                gap.closed_at = None
                gap.closure_reason = ""

        summaries.append(
            {
                "measure_code": measure_code,
                "eligible": True,
                "pdc": result.pdc,
                "adherent": result.adherent,
                "care_gap_id": gap.id,
            }
        )

    return summaries
