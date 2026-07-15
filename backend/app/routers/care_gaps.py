from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..db import get_db
from ..deps import client_ip, require_role
from ..models import (
    CareGap,
    CaseNote,
    Dependent,
    GapStatus,
    Member,
    NOTE_TYPES,
    NumeratorSource,
    ScreeningSubmission,
    StaffRole,
    StaffUser,
)
from ..schemas import CaseNoteCreate, GapStatusUpdate, NumeratorConfirm

router = APIRouter(prefix="/api/care-gaps", tags=["care_gaps"])

_ROLES = (StaffRole.care_manager.value, StaffRole.payer_admin.value, StaffRole.super_admin.value)


@router.get("/queue")
async def queue(
    status: str | None = None,
    measure: str | None = None,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """De-identified triage queue, sorted safety-first then by follow-up urgency.
    Optional `measure` filter powers the Quality Overview dashboard drill-down."""
    stmt = (
        select(CareGap, Member.alias, Dependent.alias)
        .join(Member, Member.id == CareGap.member_id)
        .outerjoin(Dependent, Dependent.id == CareGap.dependent_id)
        .where(CareGap.tenant_id == staff.tenant_id)
    )
    if status:
        stmt = stmt.where(CareGap.status == status)
    else:
        stmt = stmt.where(CareGap.status.notin_([GapStatus.closed.value, GapStatus.excluded.value]))
    if measure:
        stmt = stmt.where(CareGap.measure_code == measure)

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
            "numerator_source": gap.numerator_source,
            "follow_up_due_at": gap.follow_up_due_at,
            "member_alias": member_alias,
            "dependent_alias": dependent_alias,
        }
        for gap, member_alias, dependent_alias in rows
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
    dependent = await db.get(Dependent, gap.dependent_id) if gap.dependent_id else None
    submissions = (
        await db.execute(select(ScreeningSubmission).where(ScreeningSubmission.care_gap_id == gap.id))
    ).scalars().all()
    notes = (await db.execute(select(CaseNote).where(CaseNote.care_gap_id == gap.id))).scalars().all()

    return {
        "id": gap.id,
        "measure_code": gap.measure_code,
        "status": gap.status,
        "safety_flag": gap.safety_flag,
        "numerator_met": gap.numerator_met,
        "numerator_source": gap.numerator_source,
        "numerator_source_reference": gap.numerator_source_reference,
        "follow_up_due_at": gap.follow_up_due_at,
        "member_id": gap.member_id,  # internal UUID (no PII) — lets the workspace load screening history
        "member_alias": member.alias,
        "dependent_alias": dependent.alias if dependent else None,
        "submissions": [
            {"submitted_at": s.submitted_at, "instrument_scores": s.instrument_scores, "safety_flag": s.safety_flag}
            for s in submissions
        ],
        "notes": [
            {"id": n.id, "note": n.note, "note_type": n.note_type, "author_id": n.author_id, "created_at": n.created_at}
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
    if body.status == GapStatus.excluded.value and not body.reason.strip():
        raise HTTPException(422, "An exclusion reason is required — it's what your HEDIS auditor will ask for")

    gap.status = body.status
    if body.status in (GapStatus.closed.value, GapStatus.excluded.value):
        gap.closed_at = datetime.utcnow()
        gap.closure_reason = body.reason.strip() or "closed_by_staff"
    else:
        gap.closed_at = None
        gap.closure_reason = ""

    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="care_gap_status_updated",
        resource_type="care_gap",
        resource_id=gap.id,
        tenant_id=staff.tenant_id,
        ip_address=client_ip(request),
        metadata={"new_status": body.status, "reason": body.reason},
    )
    await db.commit()
    return {"id": gap.id, "status": gap.status}


@router.post("/{gap_id}/confirm-numerator")
async def confirm_numerator(
    gap_id: str,
    body: NumeratorConfirm,
    request: Request,
    staff: StaffUser = Depends(require_role(*_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Upgrade a numerator from self-report to claims-confirmed once staff
    have matched it against a claim or encounter — the strongest evidence
    this platform can attach to a gap short of a real claims-feed pipeline."""
    gap = await db.get(CareGap, gap_id)
    if gap is None or gap.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Not found")
    if not body.reference.strip():
        raise HTTPException(422, "A claim/encounter reference is required")

    gap.numerator_met = True
    gap.numerator_source = NumeratorSource.claims_confirmed.value
    gap.numerator_source_reference = body.reference.strip()
    if gap.status not in (GapStatus.closed.value, GapStatus.excluded.value):
        gap.status = GapStatus.completed.value
        gap.closed_at = datetime.utcnow()
        gap.closure_reason = "numerator_met_claims_confirmed"

    await log_action(
        db,
        actor_type="staff",
        actor_id=staff.id,
        action="numerator_confirmed_claims",
        resource_type="care_gap",
        resource_id=gap.id,
        tenant_id=staff.tenant_id,
        ip_address=client_ip(request),
        metadata={"reference": body.reference.strip()},
    )
    await db.commit()
    return {"id": gap.id, "status": gap.status, "numerator_source": gap.numerator_source}


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

    if body.note_type not in NOTE_TYPES:
        raise HTTPException(422, "bad note_type")

    note = CaseNote(care_gap_id=gap.id, author_id=staff.id, note=body.note, note_type=body.note_type)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return {"id": note.id, "note": note.note, "note_type": note.note_type, "created_at": note.created_at}
