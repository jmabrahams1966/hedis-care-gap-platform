from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_role
from ..models import Dependent, Member, StaffRole, StaffUser
from ..schemas import DependentCreate, DependentOut
from .members import _alias, _open_care_gaps_for_dependent

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
    against the dependent, not the guardian."""
    guardian = await db.get(Member, member_id)
    if guardian is None or guardian.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Guardian member not found")

    dependent = Dependent(
        tenant_id=guardian.tenant_id,
        guardian_member_id=guardian.id,
        external_dependent_id=body.external_dependent_id,
        first_name=body.first_name,
        last_name=body.last_name,
        date_of_birth=body.date_of_birth,
        sex=body.sex,
    )
    dependent.alias = _alias(guardian.tenant_id, body.external_dependent_id, prefix="Dependent")
    db.add(dependent)
    await db.flush()

    await _open_care_gaps_for_dependent(db, dependent)
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
