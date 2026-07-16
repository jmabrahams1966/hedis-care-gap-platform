from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..db import get_db
from ..deps import client_ip, require_role
from ..models import CarePlanGoal, Member, StaffRole, StaffUser
from ..schemas import CarePlanGoalCreate, CarePlanGoalUpdate

router = APIRouter(tags=["care_plan"])

_ROLES = (StaffRole.care_manager.value, StaffRole.payer_admin.value, StaffRole.super_admin.value)
_GOAL_STATUSES = {"open", "met", "discontinued"}


def _serialize(g: CarePlanGoal) -> dict:
    return {
        "id": g.id,
        "member_id": g.member_id,
        "care_gap_id": g.care_gap_id,
        "goal_text": g.goal_text,
        "interventions_text": g.interventions_text,
        "target_date": g.target_date,
        "status": g.status,
        "created_at": g.created_at,
        "updated_at": g.updated_at,
    }


@router.get("/api/members/{member_id}/care-plan")
async def list_goals(
    member_id: str,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(Member, member_id)
    if member is None or (staff.tenant_id and member.tenant_id != staff.tenant_id):
        raise HTTPException(404, "Member not found")
    rows = (
        await db.execute(
            select(CarePlanGoal)
            .where(CarePlanGoal.member_id == member_id)
            .order_by(CarePlanGoal.created_at.desc())
        )
    ).scalars().all()
    return [_serialize(g) for g in rows]


@router.post("/api/members/{member_id}/care-plan")
async def create_goal(
    member_id: str,
    body: CarePlanGoalCreate,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(Member, member_id)
    if member is None or (staff.tenant_id and member.tenant_id != staff.tenant_id):
        raise HTTPException(404, "Member not found")
    if not body.goal_text.strip():
        raise HTTPException(422, "A goal is required")

    goal = CarePlanGoal(
        tenant_id=member.tenant_id,
        member_id=member_id,
        care_gap_id=body.care_gap_id,
        goal_text=body.goal_text.strip(),
        interventions_text=body.interventions_text.strip(),
        target_date=body.target_date,
        created_by=staff.id,
    )
    db.add(goal)
    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="care_plan_goal_created",
        resource_type="care_plan_goal",
        resource_id="",
        tenant_id=member.tenant_id,
        ip_address=client_ip(request),
        metadata={"member_id": member_id},
    )
    await db.commit()
    await db.refresh(goal)
    return _serialize(goal)


@router.patch("/api/care-plan/{goal_id}")
async def update_goal(
    goal_id: str,
    body: CarePlanGoalUpdate,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    goal = await db.get(CarePlanGoal, goal_id)
    if goal is None or (staff.tenant_id and goal.tenant_id != staff.tenant_id):
        raise HTTPException(404, "Goal not found")
    if body.status is not None:
        if body.status not in _GOAL_STATUSES:
            raise HTTPException(422, "bad status")
        goal.status = body.status
    if body.goal_text is not None:
        goal.goal_text = body.goal_text.strip()
    if body.interventions_text is not None:
        goal.interventions_text = body.interventions_text.strip()
    if body.target_date is not None:
        goal.target_date = body.target_date
    goal.updated_at = datetime.utcnow()

    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="care_plan_goal_updated",
        resource_type="care_plan_goal",
        resource_id=goal.id,
        tenant_id=goal.tenant_id,
        ip_address=client_ip(request),
        metadata={"status": goal.status},
    )
    await db.commit()
    await db.refresh(goal)
    return _serialize(goal)
