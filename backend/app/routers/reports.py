from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_role
from ..measures import get_measure
from ..models import CareGap, GapStatus, Measure, Member, NumeratorSource, StaffRole, StaffUser, Tenant

router = APIRouter(prefix="/api/reports", tags=["reports"])

# Statuses that count as an "open" (still-actionable) gap for the dashboard.
_OPEN_STATES = [GapStatus.open.value, GapStatus.outreach_sent.value, GapStatus.needs_follow_up.value]


@router.get("/hedis")
async def hedis_rate(
    measure_code: str,
    period: str,
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    """Numerator/denominator/rate for a measure — the number payers actually care
    about maintaining. Denominator is every eligible member with a care-gap row for
    the period; numerator is those whose screening was completed."""
    measure = get_measure(measure_code)  # raises if unknown

    base = select(CareGap).where(
        CareGap.tenant_id == staff.tenant_id,
        CareGap.measure_code == measure_code,
        CareGap.period == period,
        CareGap.status != GapStatus.excluded.value,
    )
    denominator = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    numerator = (
        await db.execute(
            select(func.count()).select_from(
                base.where(CareGap.numerator_met.is_(True)).subquery()
            )
        )
    ).scalar_one()
    follow_up_due = (
        await db.execute(
            select(func.count()).select_from(
                base.where(CareGap.status == GapStatus.needs_follow_up.value).subquery()
            )
        )
    ).scalar_one()

    rate = round(numerator / denominator, 4) if denominator else 0.0
    return {
        "measure_code": measure_code,
        "hedis_measure_name": measure.hedis_measure_name,
        "period": period,
        "denominator": denominator,
        "numerator": numerator,
        "rate": rate,
        "open_follow_ups": follow_up_due,
    }


@router.get("/overview")
async def quality_overview(
    period: str,
    tenant: str | None = None,
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    """Leadership dashboard in one call: headline KPIs, per-measure performance
    (rate + self-report/claims split), and a safety-first priority worklist.
    Aggregates the tenant's care gaps for the period — no new storage. `super_admin`
    (which has no home tenant) must name one via `?tenant=<slug>`."""
    tenant_id = staff.tenant_id
    if tenant_id is None:
        if not tenant:
            raise HTTPException(400, "super_admin must pass ?tenant=<slug>")
        row = (await db.execute(select(Tenant).where(Tenant.slug == tenant))).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "Tenant not found")
        tenant_id = row.id

    gaps = (
        await db.execute(select(CareGap).where(CareGap.tenant_id == tenant_id, CareGap.period == period))
    ).scalars().all()

    # Per-measure aggregation (excluded gaps leave the denominator, mirroring /hedis).
    by_measure: dict[str, dict] = {}
    for g in gaps:
        if g.status == GapStatus.excluded.value:
            continue
        m = by_measure.setdefault(g.measure_code, {"eligible": 0, "completed": 0, "self": 0, "claims": 0})
        m["eligible"] += 1
        if g.numerator_met:
            m["completed"] += 1
            if g.numerator_source == NumeratorSource.self_report.value:
                m["self"] += 1
            elif g.numerator_source == NumeratorSource.claims_confirmed.value:
                m["claims"] += 1

    names = dict((await db.execute(select(Measure.code, Measure.hedis_measure_name))).all())
    measures = []
    for code, m in sorted(by_measure.items()):
        elig, done = m["eligible"], m["completed"]
        confirmed = m["self"] + m["claims"]
        measures.append(
            {
                "code": code,
                "name": names.get(code, code),
                "eligible": elig,
                "completed": done,
                "rate": round(done / elig, 4) if elig else 0.0,
                "remaining": elig - done,
                "source_split": {
                    "self_report": round(m["self"] / confirmed, 4) if confirmed else 0.0,
                    "claims_confirmed": round(m["claims"] / confirmed, 4) if confirmed else 0.0,
                },
                "trend_points": None,  # populated in v1.1 (MeasureSnapshot)
            }
        )

    total_elig = sum(x["eligible"] for x in measures)
    total_done = sum(x["completed"] for x in measures)
    open_safety = sum(1 for g in gaps if g.safety_flag and g.status in _OPEN_STATES)
    members_reached = len({g.member_id for g in gaps})
    members_enrolled = (
        await db.execute(select(func.count(Member.id)).where(Member.tenant_id == tenant_id))
    ).scalar_one()

    # Priority worklist: safety flags first, then needs-follow-up, then the rest.
    status_rank = {GapStatus.needs_follow_up.value: 0, GapStatus.open.value: 1, GapStatus.outreach_sent.value: 2}
    worklist_gaps = sorted(
        (g for g in gaps if g.status in _OPEN_STATES),
        key=lambda g: (0 if g.safety_flag else 1, status_rank.get(g.status, 9)),
    )[:8]
    worklist = [
        {"care_gap_id": g.id, "measure_code": g.measure_code, "status": g.status, "safety_flag": g.safety_flag}
        for g in worklist_gaps
    ]

    return {
        "period": period,
        "kpis": {
            "gap_closure_rate": round(total_done / total_elig, 4) if total_elig else 0.0,
            "open_safety_flags": open_safety,
            "bonus_at_risk": None,  # v1.1 (TenantMeasureConfig.dollar_per_gap)
            "members_reached": members_reached,
            "members_enrolled": members_enrolled,
        },
        "measures": measures,
        "worklist": worklist,
    }
