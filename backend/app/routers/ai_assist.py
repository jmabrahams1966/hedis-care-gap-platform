"""KaveraChat AI assist surfaces (Feature E, Phase 2).

Four staff-facing draft endpoints plus outcome tracking. Every endpoint returns
a DRAFT — it never sends a message, writes a note, or mutates a sequence. The
frontend shows the draft in an editable field with an "AI-generated — review
before use" label; the human sends/saves, then reports the outcome here.

All AI work goes through `AiService` (injected via `get_ai_service` so tests can
supply a fake client). When `settings.ai_enabled` is False, `AiService.run`
raises `AiDisabledError`, which every endpoint maps to HTTP 503 — the whole
feature is inert until the Bedrock IAM grant is applied.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai_service import AiDisabledError, AiService
from ..db import get_db
from ..deps import require_role
from ..models import (
    AI_OUTCOMES,
    AiInteraction,
    CareGap,
    CaseNote,
    Conversation,
    Measure,
    Member,
    Message,
    ScreeningSubmission,
    StaffRole,
    StaffUser,
    TenantMeasureConfig,
)
from ..prompts import COMPOSER_SYSTEM, OUTREACH_SYSTEM, SUMMARY_SYSTEM

router = APIRouter(tags=["ai"])

_STAFF_ROLES = (StaffRole.care_manager.value, StaffRole.payer_admin.value, StaffRole.super_admin.value)
_ADMIN_ROLES = (StaffRole.payer_admin.value, StaffRole.super_admin.value)


def get_ai_service() -> AiService:
    """Overridable in tests via app.dependency_overrides to inject a fake client."""
    return AiService()


class OutreachDraftRequest(BaseModel):
    measure_code: str
    intent: str
    channel: str = "sms"  # sms | email


class OutcomeUpdate(BaseModel):
    outcome: str  # accepted | edited | discarded


def _503_if_disabled(exc: AiDisabledError) -> HTTPException:
    return HTTPException(503, "AI assist is not enabled")


@router.post("/api/conversations/{conversation_id}/ai-draft")
async def draft_reply(
    conversation_id: str,
    staff: StaffUser = Depends(require_role(*_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
    ai: AiService = Depends(get_ai_service),
):
    """Draft a reply for the care manager based on the message thread. Does NOT
    send anything — returns {draft, interaction_id} for the composer."""
    c = await db.get(Conversation, conversation_id)
    if c is None or c.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Conversation not found")

    msgs = (
        await db.execute(
            select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at.asc())
        )
    ).scalars().all()
    transcript = "\n".join(
        f"{'Member' if m.direction == 'inbound' else 'Care team'}: {m.body}" for m in msgs
    )
    prompt = (
        "Recent secure-message thread with the member "
        "(most recent last). Draft the care team's next reply.\n\n"
        f"{transcript or '(no messages yet)'}"
    )
    try:
        result = await ai.run(
            db,
            surface="composer",
            tenant_id=staff.tenant_id,
            system=COMPOSER_SYSTEM,
            context_messages=[{"role": "user", "content": prompt}],
            actor_staff_id=staff.id,
            member_id=c.member_id,
        )
    except AiDisabledError as e:
        raise _503_if_disabled(e)
    return {"draft": result.text, "interaction_id": result.interaction_id}


@router.post("/api/members/{member_id}/ai-summary")
async def summarize_case(
    member_id: str,
    staff: StaffUser = Depends(require_role(*_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
    ai: AiService = Depends(get_ai_service),
):
    """Summarize a member's case from care gaps + notes + screening history.
    Read-only apart from the AiInteraction audit row."""
    member = await db.get(Member, member_id)
    if member is None or member.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Member not found")

    gaps = (
        await db.execute(select(CareGap).where(CareGap.member_id == member.id))
    ).scalars().all()
    gap_ids = [g.id for g in gaps]

    notes = []
    subs = []
    if gap_ids:
        notes = (
            await db.execute(
                select(CaseNote).where(CaseNote.care_gap_id.in_(gap_ids)).order_by(CaseNote.created_at.asc())
            )
        ).scalars().all()
        subs = (
            await db.execute(
                select(ScreeningSubmission)
                .where(ScreeningSubmission.care_gap_id.in_(gap_ids))
                .order_by(ScreeningSubmission.submitted_at.asc())
            )
        ).scalars().all()

    lines = ["Care gaps:"]
    for g in gaps:
        flags = []
        if g.safety_flag:
            flags.append("SAFETY FLAG")
        if g.ai_risk_level:
            flags.append(f"ai-risk={g.ai_risk_level}")
        suffix = f" [{', '.join(flags)}]" if flags else ""
        lines.append(
            f"- {g.measure_code} ({g.period}): status={g.status}, "
            f"numerator_met={g.numerator_met}{suffix}"
        )
    lines.append("\nClinical notes:")
    lines += [f"- ({n.note_type}) {n.note}" for n in notes] or ["- (none)"]
    lines.append("\nScreening history:")
    lines += [
        f"- {s.measure_code} @ {s.submitted_at:%Y-%m-%d}: {s.instrument_scores}" for s in subs
    ] or ["- (none)"]
    prompt = "Summarize this member's case for a care manager.\n\n" + "\n".join(lines)

    try:
        result = await ai.run(
            db,
            surface="summary",
            tenant_id=staff.tenant_id,
            system=SUMMARY_SYSTEM,
            context_messages=[{"role": "user", "content": prompt}],
            actor_staff_id=staff.id,
            member_id=member.id,
        )
    except AiDisabledError as e:
        raise _503_if_disabled(e)
    return {"summary": result.text, "interaction_id": result.interaction_id}


@router.post("/api/sequences/ai-draft-step")
async def draft_sequence_step(
    body: OutreachDraftRequest,
    staff: StaffUser = Depends(require_role(*_ADMIN_ROLES)),
    db: AsyncSession = Depends(get_db),
    ai: AiService = Depends(get_ai_service),
):
    """Draft outreach copy for a sequence step. Admin-only. Nothing is applied to
    a sequence — returns {draft, interaction_id} for the builder to drop in."""
    # The measure must be enabled for this tenant (also scopes the request).
    cfg = (
        await db.execute(
            select(TenantMeasureConfig).where(
                TenantMeasureConfig.tenant_id == staff.tenant_id,
                TenantMeasureConfig.measure_code == body.measure_code,
            )
        )
    ).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(404, "Measure not enabled for this tenant")
    measure = await db.get(Measure, body.measure_code)
    measure_name = measure.hedis_measure_name if measure else body.measure_code

    prompt = (
        f"HEDIS measure: {measure_name} ({body.measure_code}).\n"
        f"Channel: {body.channel}.\n"
        f"Step intent: {body.intent}\n\n"
        "Draft the outreach copy for this step."
    )
    try:
        result = await ai.run(
            db,
            surface="outreach",
            tenant_id=staff.tenant_id,
            system=OUTREACH_SYSTEM,
            context_messages=[{"role": "user", "content": prompt}],
            actor_staff_id=staff.id,
        )
    except AiDisabledError as e:
        raise _503_if_disabled(e)
    return {"draft": result.text, "interaction_id": result.interaction_id}


@router.post("/api/ai-interactions/{interaction_id}/outcome")
async def record_outcome(
    interaction_id: str,
    body: OutcomeUpdate,
    staff: StaffUser = Depends(require_role(*_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Record what the human did with a draft (accepted | edited | discarded).
    Feeds AI-quality monitoring; not gated by ai_enabled so an in-flight draft
    can still be resolved if the feature is toggled off mid-session."""
    if body.outcome not in AI_OUTCOMES or body.outcome == "generated":
        raise HTTPException(422, "outcome must be accepted, edited, or discarded")
    interaction = await db.get(AiInteraction, interaction_id)
    if interaction is None or interaction.tenant_id != staff.tenant_id:
        raise HTTPException(404, "Interaction not found")
    interaction.outcome = body.outcome
    await db.commit()
    return {"id": interaction.id, "outcome": interaction.outcome}
