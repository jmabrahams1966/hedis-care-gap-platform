from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..db import get_db
from ..deps import client_ip, require_role
from ..models import Member, SequenceEnrollment, StaffRole, StaffUser

router = APIRouter(tags=["enrollments"])

_ROLES = (StaffRole.care_manager.value, StaffRole.payer_admin.value, StaffRole.super_admin.value)


def _serialize(e: SequenceEnrollment) -> dict:
    return {
        "id": e.id,
        "member_id": e.member_id,
        "care_gap_id": e.care_gap_id,
        "sequence_id": e.sequence_id,
        "status": e.status,
        "current_step_order": e.current_step_order,
        "next_send_at": e.next_send_at,
        "ended_reason": e.ended_reason,
    }


@router.get("/api/members/{member_id}/enrollments")
async def list_enrollments(
    member_id: str,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(Member, member_id)
    if member is None or (staff.tenant_id and member.tenant_id != staff.tenant_id):
        raise HTTPException(404, "Member not found")
    rows = (
        await db.execute(
            select(SequenceEnrollment)
            .where(SequenceEnrollment.member_id == member_id)
            .order_by(SequenceEnrollment.created_at.desc())
        )
    ).scalars().all()
    return [_serialize(e) for e in rows]


async def _load(db: AsyncSession, staff: StaffUser, enrollment_id: str) -> SequenceEnrollment:
    e = await db.get(SequenceEnrollment, enrollment_id)
    if e is None or (staff.tenant_id and e.tenant_id != staff.tenant_id):
        raise HTTPException(404, "Enrollment not found")
    return e


@router.post("/api/enrollments/{enrollment_id}/pause")
async def pause_enrollment(
    enrollment_id: str,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    e = await _load(db, staff, enrollment_id)
    if e.status == "active":
        e.status = "paused"
    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="enrollment_paused",
        resource_type="sequence_enrollment",
        resource_id=e.id,
        tenant_id=e.tenant_id,
        ip_address=client_ip(request),
    )
    await db.commit()
    return _serialize(e)


@router.post("/api/enrollments/{enrollment_id}/resume")
async def resume_enrollment(
    enrollment_id: str,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    e = await _load(db, staff, enrollment_id)
    if e.status == "paused":
        e.status = "active"
    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="enrollment_resumed",
        resource_type="sequence_enrollment",
        resource_id=e.id,
        tenant_id=e.tenant_id,
        ip_address=client_ip(request),
    )
    await db.commit()
    return _serialize(e)


@router.post("/api/enrollments/{enrollment_id}/end")
async def end_enrollment(
    enrollment_id: str,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    e = await _load(db, staff, enrollment_id)
    e.status = "ended"
    e.ended_by = staff.id
    e.ended_reason = e.ended_reason or "manual"
    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="enrollment_ended",
        resource_type="sequence_enrollment",
        resource_id=e.id,
        tenant_id=e.tenant_id,
        ip_address=client_ip(request),
    )
    await db.commit()
    return _serialize(e)
