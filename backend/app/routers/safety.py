from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..db import get_db
from ..deps import client_ip, require_role
from ..models import CareGap, EscalationStep, Member, SafetyPlan, StaffRole, StaffUser
from ..schemas import SafetyPlanUpsert

router = APIRouter(tags=["safety"])

_ROLES = (StaffRole.care_manager.value, StaffRole.payer_admin.value, StaffRole.super_admin.value)

# PLACEHOLDER crisis-escalation protocol — pending clinical sign-off before any
# real clinical use (see docs/HEDIS_COMPLIANCE.md). Order is display order.
ESCALATION_STEPS: list[tuple[str, str]] = [
    ("crisis_line_provided", "988 / crisis line provided to member"),
    ("outreach_completed", "Live outreach completed (spoke with member)"),
    ("bh_warm_handoff", "Behavioral-health warm handoff arranged"),
    ("pcp_notified", "PCP / care team notified"),
]
_STEP_KEYS = {k for k, _ in ESCALATION_STEPS}
_STEP_LABELS = dict(ESCALATION_STEPS)


def _plan_dict(p: SafetyPlan | None) -> dict:
    return {
        "warning_signs": p.warning_signs if p else "",
        "coping_strategies": p.coping_strategies if p else "",
        "support_contacts": p.support_contacts if p else "",
        "means_restriction": p.means_restriction if p else "",
        "notes": p.notes if p else "",
        "updated_at": p.updated_at if p else None,
    }


@router.get("/api/members/{member_id}/safety-plan")
async def get_safety_plan(
    member_id: str,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(Member, member_id)
    if member is None or (staff.tenant_id and member.tenant_id != staff.tenant_id):
        raise HTTPException(404, "Member not found")
    plan = (
        await db.execute(select(SafetyPlan).where(SafetyPlan.member_id == member_id))
    ).scalar_one_or_none()
    return _plan_dict(plan)


@router.put("/api/members/{member_id}/safety-plan")
async def upsert_safety_plan(
    member_id: str,
    body: SafetyPlanUpsert,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(Member, member_id)
    if member is None or (staff.tenant_id and member.tenant_id != staff.tenant_id):
        raise HTTPException(404, "Member not found")
    plan = (
        await db.execute(select(SafetyPlan).where(SafetyPlan.member_id == member_id))
    ).scalar_one_or_none()
    if plan is None:
        plan = SafetyPlan(tenant_id=member.tenant_id, member_id=member_id, updated_by=staff.id)
        db.add(plan)
    plan.warning_signs = body.warning_signs
    plan.coping_strategies = body.coping_strategies
    plan.support_contacts = body.support_contacts
    plan.means_restriction = body.means_restriction
    plan.notes = body.notes
    plan.updated_by = staff.id
    plan.updated_at = datetime.utcnow()

    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="safety_plan_upserted",
        resource_type="safety_plan",
        resource_id=member_id,
        tenant_id=member.tenant_id,
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(plan)
    return _plan_dict(plan)


async def _gap_for_staff(db: AsyncSession, staff: StaffUser, care_gap_id: str) -> CareGap:
    gap = await db.get(CareGap, care_gap_id)
    if gap is None or (staff.tenant_id and gap.tenant_id != staff.tenant_id):
        raise HTTPException(404, "Care gap not found")
    return gap


@router.get("/api/care-gaps/{care_gap_id}/escalation")
async def get_escalation(
    care_gap_id: str,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """The fixed protocol checklist with each step's completion state (missing
    steps report as incomplete)."""
    gap = await _gap_for_staff(db, staff, care_gap_id)
    rows = (
        await db.execute(select(EscalationStep).where(EscalationStep.care_gap_id == gap.id))
    ).scalars().all()
    by_key = {r.step_key: r for r in rows}
    return [
        {
            "step_key": key,
            "label": label,
            "completed": bool(by_key.get(key) and by_key[key].completed),
            "completed_by": by_key[key].completed_by if key in by_key else None,
            "completed_at": by_key[key].completed_at if key in by_key else None,
        }
        for key, label in ESCALATION_STEPS
    ]


@router.post("/api/care-gaps/{care_gap_id}/escalation/{step_key}")
async def toggle_escalation_step(
    care_gap_id: str,
    step_key: str,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    gap = await _gap_for_staff(db, staff, care_gap_id)
    if step_key not in _STEP_KEYS:
        raise HTTPException(422, "unknown escalation step")

    row = (
        await db.execute(
            select(EscalationStep).where(
                EscalationStep.care_gap_id == gap.id, EscalationStep.step_key == step_key
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = EscalationStep(tenant_id=gap.tenant_id, care_gap_id=gap.id, step_key=step_key)
        db.add(row)

    row.completed = not row.completed
    row.completed_by = staff.id if row.completed else None
    row.completed_at = datetime.utcnow() if row.completed else None

    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="escalation_step_toggled",
        resource_type="escalation_step",
        resource_id=gap.id,
        tenant_id=gap.tenant_id,
        ip_address=client_ip(request),
        metadata={"step_key": step_key, "completed": row.completed},
    )
    await db.commit()
    return {
        "step_key": step_key,
        "label": _STEP_LABELS[step_key],
        "completed": row.completed,
        "completed_by": row.completed_by,
        "completed_at": row.completed_at,
    }
