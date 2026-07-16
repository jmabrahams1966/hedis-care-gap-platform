from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..db import get_db
from ..deps import client_ip, require_role
from ..models import CareTask, Member, StaffRole, StaffUser
from ..schemas import CareTaskCreate, CareTaskUpdate

router = APIRouter(tags=["tasks"])

_ROLES = (StaffRole.care_manager.value, StaffRole.payer_admin.value, StaffRole.super_admin.value)
_TASK_STATUSES = {"open", "done", "cancelled"}


def _serialize(t: CareTask) -> dict:
    return {
        "id": t.id,
        "member_id": t.member_id,
        "care_gap_id": t.care_gap_id,
        "title": t.title,
        "due_at": t.due_at,
        "sla_hours": t.sla_hours,
        "assignee_staff_id": t.assignee_staff_id,
        "status": t.status,
        "created_at": t.created_at,
        "completed_at": t.completed_at,
        "overdue": bool(t.due_at and t.status == "open" and t.due_at < datetime.utcnow()),
    }


@router.post("/api/members/{member_id}/tasks")
async def create_task(
    member_id: str,
    body: CareTaskCreate,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(Member, member_id)
    if member is None or (staff.tenant_id and member.tenant_id != staff.tenant_id):
        raise HTTPException(404, "Member not found")
    if not body.title.strip():
        raise HTTPException(422, "A task title is required")

    task = CareTask(
        tenant_id=member.tenant_id,
        member_id=member_id,
        care_gap_id=body.care_gap_id,
        title=body.title.strip(),
        due_at=body.due_at,
        sla_hours=body.sla_hours,
        assignee_staff_id=body.assignee_staff_id,
        created_by=staff.id,
    )
    db.add(task)
    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="care_task_created",
        resource_type="care_task",
        resource_id="",
        tenant_id=member.tenant_id,
        ip_address=client_ip(request),
        metadata={"member_id": member_id, "title": task.title},
    )
    await db.commit()
    await db.refresh(task)
    return _serialize(task)


@router.get("/api/members/{member_id}/tasks")
async def list_member_tasks(
    member_id: str,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(Member, member_id)
    if member is None or (staff.tenant_id and member.tenant_id != staff.tenant_id):
        raise HTTPException(404, "Member not found")
    rows = (
        await db.execute(
            select(CareTask).where(CareTask.member_id == member_id).order_by(CareTask.created_at.desc())
        )
    ).scalars().all()
    return [_serialize(t) for t in rows]


@router.patch("/api/tasks/{task_id}")
async def update_task(
    task_id: str,
    body: CareTaskUpdate,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(CareTask, task_id)
    if task is None or (staff.tenant_id and task.tenant_id != staff.tenant_id):
        raise HTTPException(404, "Task not found")
    if body.status not in _TASK_STATUSES:
        raise HTTPException(422, "bad status")

    task.status = body.status
    task.completed_at = datetime.utcnow() if body.status == "done" else None

    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="care_task_updated",
        resource_type="care_task",
        resource_id=task.id,
        tenant_id=task.tenant_id,
        ip_address=client_ip(request),
        metadata={"new_status": body.status},
    )
    await db.commit()
    await db.refresh(task)
    return _serialize(task)


@router.get("/api/tasks")
async def list_tasks(
    status: str | None = None,
    assignee: str | None = None,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Cross-member task rollup for the tenant. `status=overdue` returns open
    tasks past their due date; `assignee=me` narrows to the caller's tasks."""
    stmt = select(CareTask).where(CareTask.tenant_id == staff.tenant_id)
    if status == "overdue":
        stmt = stmt.where(
            CareTask.status == "open",
            CareTask.due_at.is_not(None),
            CareTask.due_at < datetime.utcnow(),
        )
    elif status:
        stmt = stmt.where(CareTask.status == status)
    if assignee == "me":
        stmt = stmt.where(CareTask.assignee_staff_id == staff.id)
    rows = (await db.execute(stmt.order_by(CareTask.due_at.asc().nulls_last()))).scalars().all()
    return [_serialize(t) for t in rows]
