from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_role
from ..models import Dependent, Member, StaffRole, StaffUser
from ..schemas import DependentCreate, DependentOut
from .members import _create_dependent

router = APIRouter(prefix="/api/members", tags=["dependents"])


@router.post("/{member_id}/dependents", response_model=DependentOut)
async def create_dependent(
    member_id: str,
    body: DependentCreate,
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    """Register a minor dependent under a guardian member — the account
    holder who already receives outreach continues to; pediatric measures
    (Childhood Immunization Status, Well-Child Visits) evaluate eligibility
    against the dependent, not the guardian. For loading many dependents at
    once, see POST /api/members/bulk-csv instead."""
    guardian = await db.get(Member, member_id)
    if guardian is None or guardian.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Guardian member not found")

    dependent = await _create_dependent(db, guardian, body)
    await db.commit()
    await db.refresh(dependent)
    return dependent


@router.get("/{member_id}/dependents", response_model=list[DependentOut])
async def list_dependents(
    member_id: str,
    staff: StaffUser = Depends(
        require_role(StaffRole.payer_admin.value, StaffRole.care_manager.value, StaffRole.super_admin.value)
    ),
    db: AsyncSession = Depends(get_db),
):
    guardian = await db.get(Member, member_id)
    if guardian is None or guardian.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Guardian member not found")

    res = await db.execute(select(Dependent).where(Dependent.guardian_member_id == member_id))
    return res.scalars().all()
