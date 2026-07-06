from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..db import get_db
from ..deps import client_ip, get_current_member
from ..measures import get_measure
from ..models import CareGap, Dependent, GapStatus, Member, ScreeningSubmission
from ..schemas import ScreeningSubmit

router = APIRouter(prefix="/api/screenings", tags=["screenings"])


@router.get("/pending")
async def list_pending_screenings(
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """A guardian's pending list includes both their own care gaps and any of
    their dependents' (pediatric measures) — dependent_first_name lets the
    frontend personalize the question ("Has Emma had her checkup?" vs "Have
    you...")."""
    res = await db.execute(
        select(CareGap, Dependent)
        .outerjoin(Dependent, Dependent.id == CareGap.dependent_id)
        .where(
            CareGap.member_id == member.id,
            CareGap.status.in_([GapStatus.open.value, GapStatus.outreach_sent.value]),
        )
    )
    rows = res.all()
    return [
        {
            "care_gap_id": gap.id,
            "measure_code": gap.measure_code,
            "period": gap.period,
            "dependent_first_name": dependent.first_name if dependent else None,
        }
        for gap, dependent in rows
    ]


@router.post("")
async def submit_screening(
    body: ScreeningSubmit,
    request: Request,
    member: Member = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    gap = await db.get(CareGap, body.care_gap_id)
    if gap is None or gap.member_id != member.id:
        raise HTTPException(404, "Care gap not found")
    if gap.status == GapStatus.closed.value:
        raise HTTPException(409, "This care gap is already closed")

    measure = get_measure(gap.measure_code)
    try:
        evaluation = measure.evaluate_submission(body.responses)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, str(e))

    submission = ScreeningSubmission(
        care_gap_id=gap.id,
        member_id=member.id,
        measure_code=gap.measure_code,
        instrument_scores=evaluation["instrument_scores"],
        safety_flag=evaluation["safety_flag"],
    )
    db.add(submission)

    gap.numerator_met = evaluation["numerator_met"]
    gap.safety_flag = evaluation["safety_flag"]
    window_days = measure.follow_up_window_days(evaluation)
    if window_days is not None:
        gap.status = GapStatus.needs_follow_up.value
        gap.follow_up_due_at = datetime.utcnow() + timedelta(days=window_days)
    elif gap.numerator_met:
        gap.status = GapStatus.completed.value
        gap.closed_at = datetime.utcnow()
        gap.closure_reason = "numerator_met"
    else:
        # Member responded but the numerator isn't met and no follow-up window
        # applies (e.g. BCS: hasn't been screened, doesn't want scheduling help
        # yet) — leave the gap open so normal outreach cadence keeps nudging.
        gap.status = GapStatus.open.value

    await log_action(
        db,
        actor_type="member",
        actor_id=member.id,
        action="screening_submitted",
        resource_type="care_gap",
        resource_id=gap.id,
        tenant_id=member.tenant_id,
        ip_address=client_ip(request),
        metadata={"measure_code": gap.measure_code, "safety_flag": evaluation["safety_flag"]},
    )
    await db.commit()

    return {
        "status": gap.status,
        "safety_flag": evaluation["safety_flag"],
        "needs_follow_up": window_days is not None,
    }
