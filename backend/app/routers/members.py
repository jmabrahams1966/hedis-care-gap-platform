import hashlib
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_role
from ..measures import REGISTRY
from ..models import CareGap, Member, StaffRole, StaffUser, TenantMeasureConfig
from ..measures.base import default_period
from ..schemas import MemberCreate, MemberOut

router = APIRouter(prefix="/api/members", tags=["members"])


def _alias(tenant_id: str, external_member_id: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}:{external_member_id}".encode()).hexdigest()[:6].upper()
    return f"Member-{digest}"


async def _open_care_gaps_for_member(db: AsyncSession, member: Member) -> None:
    """Evaluate every measure enabled for the member's tenant and open a CareGap
    row for the current period if the member is eligible and doesn't have one yet."""
    configs = (
        await db.execute(
            select(TenantMeasureConfig).where(
                TenantMeasureConfig.tenant_id == member.tenant_id,
                TenantMeasureConfig.enabled.is_(True),
            )
        )
    ).scalars().all()

    period = default_period()
    for config in configs:
        measure = REGISTRY.get(config.measure_code)
        if measure is None or not measure.is_eligible(member, date.today()):
            continue
        existing = (
            await db.execute(
                select(CareGap).where(
                    CareGap.member_id == member.id,
                    CareGap.measure_code == config.measure_code,
                    CareGap.period == period,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                CareGap(
                    tenant_id=member.tenant_id,
                    member_id=member.id,
                    measure_code=config.measure_code,
                    period=period,
                )
            )


@router.post("", response_model=MemberOut)
async def create_member(
    body: MemberCreate,
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    if staff.role != StaffRole.super_admin.value and staff.tenant_id is None:
        raise HTTPException(403, "Staff user has no tenant")
    tenant_id = staff.tenant_id

    member = Member(
        tenant_id=tenant_id,
        external_member_id=body.external_member_id,
        first_name=body.first_name,
        last_name=body.last_name,
        date_of_birth=body.date_of_birth,
        phone=body.phone,
        email=body.email,
        preferred_channel=body.preferred_channel,
        preferred_language=body.preferred_language,
        consent_sms=body.consent_sms,
        consent_email=body.consent_email,
    )
    member.alias = _alias(tenant_id, body.external_member_id)
    db.add(member)
    await db.flush()

    await _open_care_gaps_for_member(db, member)
    await db.commit()
    await db.refresh(member)
    return member


@router.post("/bulk", response_model=list[MemberOut])
async def bulk_create_members(
    body: list[MemberCreate],
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    """Roster ingestion endpoint — accepts a batch from the payer's eligibility feed."""
    created = []
    for item in body:
        member = Member(
            tenant_id=staff.tenant_id,
            external_member_id=item.external_member_id,
            first_name=item.first_name,
            last_name=item.last_name,
            date_of_birth=item.date_of_birth,
            phone=item.phone,
            email=item.email,
            preferred_channel=item.preferred_channel,
            preferred_language=item.preferred_language,
            consent_sms=item.consent_sms,
            consent_email=item.consent_email,
        )
        member.alias = _alias(staff.tenant_id, item.external_member_id)
        db.add(member)
        await db.flush()
        await _open_care_gaps_for_member(db, member)
        created.append(member)
    await db.commit()
    for member in created:
        await db.refresh(member)
    return created


@router.get("", response_model=list[MemberOut])
async def list_members(
    staff: StaffUser = Depends(
        require_role(StaffRole.payer_admin.value, StaffRole.care_manager.value, StaffRole.super_admin.value)
    ),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Member).where(Member.tenant_id == staff.tenant_id))
    return res.scalars().all()
