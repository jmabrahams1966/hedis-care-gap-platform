from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_role
from ..models import CareGap, GapStatus, Member, OutreachStatus, StaffRole, StaffUser, Tenant
from ..outreach_service import RETRY_CADENCE_DAYS, run_batch_for_tenant, send_to_member

router = APIRouter(prefix="/api/outreach", tags=["outreach"])

_ROLES = (StaffRole.care_manager.value, StaffRole.payer_admin.value, StaffRole.super_admin.value)


@router.post("/send/{gap_id}")
async def send_outreach(
    gap_id: str,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    gap = await db.get(CareGap, gap_id)
    if gap is None or gap.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Not found")
    tenant = await db.get(Tenant, staff.tenant_id)
    member = await db.get(Member, gap.member_id)

    attempt = await send_to_member(db, tenant, member, gap)
    if attempt.status == OutreachStatus.sent.value:
        gap.status = GapStatus.outreach_sent.value
        gap.last_outreach_at = datetime.utcnow()
        gap.next_outreach_at = datetime.utcnow() + timedelta(days=RETRY_CADENCE_DAYS)
    await db.commit()
    return {"gap_id": gap.id, "outreach_status": attempt.status, "channel": attempt.channel}


@router.post("/run-batch")
async def run_batch(
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    """Sends outreach for every open gap in the caller's tenant due for (re)contact.
    For all tenants at once on a schedule, see app/scripts/run_outreach_cron.py —
    this endpoint stays tenant-scoped so a payer_admin can only trigger their own."""
    tenant = await db.get(Tenant, staff.tenant_id)
    return await run_batch_for_tenant(db, tenant)
