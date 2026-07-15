"""Open Prenatal and Postpartum Care (PPC) gaps for a member from a delivery
episode. The data-driven counterpart to `_open_care_gaps_for_member` for PPC —
gaps are anchored to a `PregnancyEpisode`'s delivery date, and the postpartum
gap's outreach is timed to the 7–84-day-after-delivery window.

Simplification: the gap is keyed to (member × measure × delivery-year), so a
member with two deliveries in the same year would need the >60-day-apart episode
handling the real HEDIS spec has — flagged in docs/HEDIS_COMPLIANCE.md, not
handled here.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CareGap, Member, PregnancyEpisode, TenantMeasureConfig
from .exclusions import is_excluded, member_exclusion_codes
from .prenatal_postpartum import PPC_MEASURES, postpartum_care_measure

# A postpartum visit counts on days 7–84 after delivery; start nudging when the
# window opens.
POSTPARTUM_WINDOW_START_DAYS = 7
POSTPARTUM_WINDOW_END_DAYS = 84


def _parse(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def measurement_year_for_delivery(delivery: date) -> int:
    """HEDIS PPC uses a denominator window of Oct 8 (Y-1) through Oct 7 (Y) so
    that a delivery and its 84-day postpartum window fall in the same
    measurement year Y. A late-year delivery (on/after Oct 8) therefore belongs
    to the *next* calendar year's measurement period, which is where its
    January-ish postpartum visit will be counted."""
    if (delivery.month, delivery.day) >= (10, 8):
        return delivery.year + 1
    return delivery.year


async def _enabled_ppc_codes(db: AsyncSession, tenant_id: str) -> set[str]:
    rows = (
        await db.execute(
            select(TenantMeasureConfig.measure_code).where(
                TenantMeasureConfig.tenant_id == tenant_id,
                TenantMeasureConfig.enabled.is_(True),
            )
        )
    ).scalars().all()
    return set(rows) & {m.code for m in PPC_MEASURES}


async def open_ppc_gaps_for_episode(
    db: AsyncSession, member: Member, episode: PregnancyEpisode
) -> list[dict]:
    """Open the enabled PPC gaps for one delivery episode. Idempotent — an
    existing gap for the member/measure/delivery-year is left as-is. Does not
    commit; the caller owns the transaction."""
    delivery = _parse(episode.delivery_date)
    if delivery is None:
        return []

    enabled = await _enabled_ppc_codes(db, member.tenant_id)
    if not enabled:
        return []

    # Period is the HEDIS measurement year for this delivery, not just its
    # calendar year — so a December delivery's postpartum visit is reported in
    # the year it actually happens.
    period = str(measurement_year_for_delivery(delivery))
    exclusion_codes = await member_exclusion_codes(db, member.id)
    summaries: list[dict] = []
    for measure in PPC_MEASURES:
        if measure.code not in enabled:
            continue
        if is_excluded(exclusion_codes, measure):
            continue  # broad exclusion (hospice/deceased) — not in the denominator

        # Gaps are keyed to the delivery episode, so a member with two deliveries
        # in one measurement year gets two independent PPC gaps.
        gap = (
            await db.execute(
                select(CareGap).where(
                    CareGap.pregnancy_episode_id == episode.id,
                    CareGap.measure_code == measure.code,
                )
            )
        ).scalar_one_or_none()

        created = gap is None
        if created:
            gap = CareGap(
                tenant_id=member.tenant_id,
                member_id=member.id,
                measure_code=measure.code,
                period=period,
                pregnancy_episode_id=episode.id,
            )
            if measure.code == postpartum_care_measure.code:
                # Time the first postpartum nudge to when the 7-day window opens
                # (or now, if delivery was already more than a week ago).
                window_open = max(delivery + timedelta(days=POSTPARTUM_WINDOW_START_DAYS), date.today())
                gap.next_outreach_at = datetime.combine(window_open, datetime.min.time())
            db.add(gap)
            await db.flush()

        summaries.append(
            {"measure_code": measure.code, "care_gap_id": gap.id, "period": period, "opened": created}
        )

    return summaries
