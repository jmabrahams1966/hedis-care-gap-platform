from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..db import get_db
from ..deps import client_ip, require_role
from ..models import CareGap, CaseNote, GapStatus, Member, ScreeningSubmission, StaffRole, StaffUser
from ..schemas import CaseNoteCreate, GapStatusUpdate

router = APIRouter(prefix="/api/care-gaps", tags=["care_gaps"])

_ROLES = (StaffRole.care_manager.value, StaffRole.payer_admin.value, StaffRole.super_admin.value)


@router.get("/queue")
async def queue(
    status: str | None = None,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """De-identified triage queue, sorted safety-first then by follow-up urgency."""
    stmt = (
        select(CareGap, Member.alias)
        .join(Member, Member.id == CareGap.member_id)
        .where(CareGap.tenant_id == staff.tenant_id)
    )
    if status:
        stmt = stmt.where(CareGap.status == status)
    else:
        stmt = stmt.where(CareGap.status != GapStatus.closed.value)

    stmt = stmt.order_by(
        case((CareGap.safety_flag.is_(True), 0), else_=1),
        case((CareGap.status == GapStatus.needs_follow_up.value, 0), else_=1),
        CareGap.follow_up_due_at.asc().nulls_last(),
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": gap.id,
            "measure_code": gap.measure_code,
            "period": gap.period,
            "status": gap.status,
            "safety_flag": gap.safety_flag,
            "numerator_met": gap.numerator_met,
            "follow_up_due_at": gap.follow_up_due_at,
            "member_alias": alias,
        }
        for gap, alias in rows
    ]


@router.get("/{gap_id}")
async def case_detail(
    gap_id: str,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    gap = await db.get(CareGap, gap_id)
    if gap is None or gap.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Not found")
    member = await db.get(Member, gap.member_id)
    submissions = (
        await db.execute(select(ScreeningSubmission).where(ScreeningSubmission.care_gap_id == gap.id))
    ).scalars().all()
    notes = (await db.execute(select(CaseNote).where(CaseNote.care_gap_id == gap.id))).scalars().all()

    return {
        "id": gap.id,
        "measure_code": gap.measure_code,
        "status": gap.status,
        "safety_flag": gap.safety_flag,
        "follow_up_due_at": gap.follow_up_due_at,
        "member_alias": member.alias,
        "submissions": [
            {"submitted_at": s.submitted_at, "instrument_scores": s.instrument_scores, "safety_flag": s.safety_flag}
            for s in submissions
        ],
        "notes": [
            {"id": n.id, "note": n.note, "author_id": n.author_id, "created_at": n.created_at}
            for n in notes
        ],
    }


@router.patch("/{gap_id}/status")
async def update_status(
    gap_id: str,
    body: GapStatusUpdate,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    gap = await db.get(CareGap, gap_id)
    if gap is None or gap.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Not found")
    if body.status not in {s.value for s in GapStatus}:
        raise HTTPException(422, "Invalid status")

    gap.status = body.status
    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="care_gap_status_updated",
        resource_type="care_gap",
        resource_id=gap.id,
        tenant_id=staff.tenant_id,
        ip_address=client_ip(request),
        metadata={"new_status": body.status},
    )
    await db.commit()
    return {"id": gap.id, "status": gap.status}


@router.post("/{gap_id}/notes")
async def add_note(
    gap_id: str,
    body: CaseNoteCreate,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    gap = await db.get(CareGap, gap_id)
    if gap is None or gap.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Not found")

    note = CaseNote(care_gap_id=gap.id, author_id=staff.id, note=body.note)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return {"id": note.id, "note": note.note, "created_at": note.created_at}
