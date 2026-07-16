from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..db import get_db
from ..deps import client_ip, require_role
from ..models import (
    OutreachSequence,
    SequenceStep,
    StaffRole,
    StaffUser,
    TenantMeasureConfig,
)
from ..schemas import MeasureSequenceAssign, SequenceCreate, SequenceUpdate

router = APIRouter(tags=["sequences"])

_ROLES = (StaffRole.payer_admin.value, StaffRole.super_admin.value)
_CHANNELS = {"sms", "email", "member_preferred"}


def _serialize(seq: OutreachSequence, steps: list[SequenceStep]) -> dict:
    return {
        "id": seq.id,
        "tenant_id": seq.tenant_id,
        "name": seq.name,
        "is_default": seq.is_default,
        "is_template": seq.tenant_id is None,
        "steps": [
            {
                "step_order": s.step_order,
                "offset_days": s.offset_days,
                "channel": s.channel,
                "template_key": s.template_key,
                "recurring": s.recurring,
                "repeat_interval_days": s.repeat_interval_days,
            }
            for s in sorted(steps, key=lambda s: s.step_order)
        ],
    }


async def _steps(db: AsyncSession, sequence_id: str) -> list[SequenceStep]:
    return list(
        (
            await db.execute(select(SequenceStep).where(SequenceStep.sequence_id == sequence_id))
        ).scalars().all()
    )


def _validate_steps(steps) -> None:
    orders = [s.step_order for s in steps]
    if len(orders) != len(set(orders)):
        raise HTTPException(422, "duplicate step_order")
    for s in steps:
        if s.channel not in _CHANNELS:
            raise HTTPException(422, f"bad channel {s.channel}")
        if s.recurring and not s.repeat_interval_days:
            raise HTTPException(422, "recurring step needs repeat_interval_days")


@router.get("/api/sequences")
async def list_sequences(
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """The tenant's own sequences plus platform templates (tenant_id NULL)."""
    rows = (
        await db.execute(
            select(OutreachSequence).where(
                or_(OutreachSequence.tenant_id == staff.tenant_id, OutreachSequence.tenant_id.is_(None))
            )
        )
    ).scalars().all()
    return [_serialize(s, await _steps(db, s.id)) for s in rows]


@router.post("/api/sequences")
async def create_sequence(
    body: SequenceCreate,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    if not body.name.strip():
        raise HTTPException(422, "A sequence name is required")
    _validate_steps(body.steps)
    seq = OutreachSequence(
        tenant_id=staff.tenant_id, name=body.name.strip(), is_default=body.is_default, created_by=staff.id
    )
    db.add(seq)
    await db.flush()
    for s in body.steps:
        db.add(SequenceStep(sequence_id=seq.id, **s.model_dump()))
    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="sequence_created",
        resource_type="outreach_sequence",
        resource_id=seq.id,
        tenant_id=staff.tenant_id,
        ip_address=client_ip(request),
    )
    await db.commit()
    return _serialize(seq, await _steps(db, seq.id))


async def _owned(db: AsyncSession, staff: StaffUser, sequence_id: str) -> OutreachSequence:
    seq = await db.get(OutreachSequence, sequence_id)
    if seq is None:
        raise HTTPException(404, "Sequence not found")
    # Platform templates (tenant_id NULL) are read-only; tenants can only mutate their own.
    if seq.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Sequence not found")
    return seq


@router.get("/api/sequences/{sequence_id}")
async def get_sequence(
    sequence_id: str,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    seq = await db.get(OutreachSequence, sequence_id)
    if seq is None or (seq.tenant_id not in (None, staff.tenant_id)):
        raise HTTPException(404, "Sequence not found")
    return _serialize(seq, await _steps(db, seq.id))


@router.put("/api/sequences/{sequence_id}")
async def update_sequence(
    sequence_id: str,
    body: SequenceUpdate,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    seq = await _owned(db, staff, sequence_id)
    _validate_steps(body.steps)
    seq.name = body.name.strip()
    # Replace the step set wholesale — simplest correct semantics for a builder UI.
    for old in await _steps(db, seq.id):
        await db.delete(old)
    await db.flush()
    for s in body.steps:
        db.add(SequenceStep(sequence_id=seq.id, **s.model_dump()))
    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="sequence_updated",
        resource_type="outreach_sequence",
        resource_id=seq.id,
        tenant_id=staff.tenant_id,
        ip_address=client_ip(request),
    )
    await db.commit()
    return _serialize(seq, await _steps(db, seq.id))


@router.delete("/api/sequences/{sequence_id}")
async def delete_sequence(
    sequence_id: str,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    seq = await _owned(db, staff, sequence_id)
    for old in await _steps(db, seq.id):
        await db.delete(old)
    await db.delete(seq)
    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="sequence_deleted",
        resource_type="outreach_sequence",
        resource_id=sequence_id,
        tenant_id=staff.tenant_id,
        ip_address=client_ip(request),
    )
    await db.commit()
    return {"status": "deleted"}


@router.patch("/api/measures/{measure_code}/sequence")
async def assign_sequence_to_measure(
    measure_code: str,
    body: MeasureSequenceAssign,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Assign (or clear) the outreach sequence a measure auto-enrolls new gaps into."""
    cfg = (
        await db.execute(
            select(TenantMeasureConfig).where(
                TenantMeasureConfig.tenant_id == staff.tenant_id,
                TenantMeasureConfig.measure_code == measure_code,
            )
        )
    ).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(404, "Measure not enabled for this tenant")
    if body.sequence_id is not None:
        seq = await db.get(OutreachSequence, body.sequence_id)
        if seq is None or seq.tenant_id not in (None, staff.tenant_id):
            raise HTTPException(404, "Sequence not found")
    cfg.sequence_id = body.sequence_id
    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="measure_sequence_assigned",
        resource_type="tenant_measure_config",
        resource_id=cfg.id,
        tenant_id=staff.tenant_id,
        ip_address=client_ip(request),
        metadata={"measure_code": measure_code, "sequence_id": body.sequence_id},
    )
    await db.commit()
    return {"measure_code": measure_code, "sequence_id": cfg.sequence_id}
