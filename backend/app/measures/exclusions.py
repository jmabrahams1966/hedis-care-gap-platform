"""HEDIS exclusions — members removed from a measure's denominator.

Two kinds:
- **Broad** (hospice, deceased, palliative care) — remove a member from *every*
  measure. Defined here.
- **Measure-specific** — declared per measure via `Measure.exclusion_codes`
  (e.g. a hysterectomy excludes cervical screening).

The `MemberExclusion` rows record *what happened* (the exclusion event + a
claim/encounter reference an auditor can check); the mapping from an event to
the measures it removes lives in code (here + on the measures), keeping data and
policy separate.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

#: Exclusions that remove a member from every measure's denominator.
BROAD_EXCLUSION_CODES = frozenset({"hospice", "deceased", "palliative_care"})


def all_known_exclusion_codes() -> set[str]:
    """Every exclusion code the platform understands — broad plus every measure's
    own. Used to reject typos at ingestion (an unknown code would silently
    exclude nothing)."""
    from . import REGISTRY  # local import to avoid an import cycle

    codes = set(BROAD_EXCLUSION_CODES)
    for measure in REGISTRY.values():
        codes |= getattr(measure, "exclusion_codes", frozenset())
    return codes


def excluding_codes_for(measure) -> frozenset[str]:
    """The exclusion codes that remove a member from this measure — the broad
    set plus the measure's own."""
    return BROAD_EXCLUSION_CODES | getattr(measure, "exclusion_codes", frozenset())


def is_excluded(member_codes: set[str], measure) -> bool:
    return bool(set(member_codes) & excluding_codes_for(measure))


async def member_exclusion_codes(db: AsyncSession, member_id: str) -> set[str]:
    from ..models import MemberExclusion

    rows = (
        await db.execute(
            select(MemberExclusion.exclusion_code).where(MemberExclusion.member_id == member_id)
        )
    ).scalars().all()
    return set(rows)


async def apply_exclusions_for_member(db: AsyncSession, member) -> int:
    """Mark a member's currently-active care gaps excluded for any measure their
    exclusions cover. Used after ingesting exclusions so a member who becomes
    e.g. hospice-enrolled stops being chased. Completed/closed gaps are left
    alone — this is about not pursuing open work — and already-excluded gaps are
    skipped. Returns the number of gaps newly excluded. Does not commit."""
    from datetime import datetime

    from ..models import CareGap, GapStatus
    from . import REGISTRY

    codes = await member_exclusion_codes(db, member.id)
    if not codes:
        return 0

    active = (GapStatus.open.value, GapStatus.outreach_sent.value, GapStatus.needs_follow_up.value)
    gaps = (
        await db.execute(
            select(CareGap).where(CareGap.member_id == member.id, CareGap.status.in_(active))
        )
    ).scalars().all()

    excluded = 0
    for gap in gaps:
        measure = REGISTRY.get(gap.measure_code)
        if measure is None or not is_excluded(codes, measure):
            continue
        applicable = sorted(codes & excluding_codes_for(measure))
        gap.status = GapStatus.excluded.value
        gap.closed_at = datetime.utcnow()
        gap.closure_reason = f"hedis_exclusion:{','.join(applicable)}"
        excluded += 1
    return excluded
