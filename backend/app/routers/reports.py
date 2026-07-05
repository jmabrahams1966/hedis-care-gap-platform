from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_role
from ..measures import get_measure
from ..models import CareGap, GapStatus, StaffRole, StaffUser

router = APIRouter(prefix="/api/reports", tags=["reports"])


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
