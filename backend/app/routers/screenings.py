from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..db import get_db
from ..deps import client_ip, get_current_member
from ..measures import REGISTRY, get_measure
from ..models import CareGap, Dependent, GapStatus, Member, NumeratorSource, ScreeningSubmission
from ..schemas import ScreeningSubmit

router = APIRouter(prefix="/api/screenings", tags=["screenings"])

# Order the member's check-in list by clinical time-sensitivity: time-bound
# maternity first, then chronic-condition measures that can surface an urgent
# reading, then behavioral health, screenings, the diabetes bundle, and
# pediatric. Anything unlisted sorts last. (A gap the outreach specifically
# targeted is opened first by the frontend regardless of this order.)
_SCREENING_PRIORITY = [
    "ppc_postpartum",
    "ppc_prenatal",
    "blood_pressure",
    "diabetes_a1c",
    "mental_health",
    "breast_cancer",
    "cervical_cancer",
    "colorectal_cancer",
    "eye_exam",
    "kidney_health",
    "childhood_immunization",
    "well_child_visits",
]


def _screening_priority(measure_code: str) -> int:
    try:
        return _SCREENING_PRIORITY.index(measure_code)
    except ValueError:
        return len(_SCREENING_PRIORITY)


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
    pending = [
        (gap, dependent)
        for gap, dependent in res.all()
        # Measures with no member-facing form (PDC — numerator computed from
        # claims) never belong in a member's "screenings to complete" list.
        # Episode-opened measures that DO accept self-report (PPC) still appear.
        if getattr(REGISTRY.get(gap.measure_code), "accepts_self_report", True)
    ]
    pending.sort(key=lambda row: _screening_priority(row[0].measure_code))
    return [
        {
            "care_gap_id": gap.id,
            "measure_code": gap.measure_code,
            "period": gap.period,
            "dependent_first_name": dependent.first_name if dependent else None,
        }
        for gap, dependent in pending
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
    if not measure.accepts_self_report:
        raise HTTPException(
            422,
            "This measure's numerator is computed from pharmacy/claims data, not a member self-report",
        )
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

    # A claims-confirmed numerator is stronger evidence than a self-report —
    # a later, possibly-contradicting self-report shouldn't be able to undo it.
    if gap.numerator_source != NumeratorSource.claims_confirmed.value:
        gap.numerator_met = evaluation["numerator_met"]
        gap.numerator_source = (
            NumeratorSource.self_report.value if gap.numerator_met else NumeratorSource.unconfirmed.value
        )
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
