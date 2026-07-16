import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..cadence_service import end_active_enrollments_for_member
from ..db import get_db
from ..models import Member
from ..notifications.sns_verify import confirm_subscription, verify_sns_signature

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Standard carrier-recognized opt-out/opt-in keywords (CTIA guidelines / TCPA practice).
STOP_KEYWORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "REVOKE"}
START_KEYWORDS = {"START", "YES", "UNSTOP"}


@router.post("/sms-inbound")
async def sms_inbound(request: Request, db: AsyncSession = Depends(get_db)):
    """Two-way SMS receiver, wired to AWS End User Messaging via an SNS HTTPS
    subscription (see infra/modules/messaging). Handles STOP/START keyword
    replies so Member.consent_sms actually reflects what the member asked
    for — AWS's own carrier-level opt-out list keeps us from re-sending
    regardless, but it doesn't update our consent record or audit trail,
    which is what HIPAA/TCPA documentation actually needs to show ("member
    revoked consent on this date").
    """
    try:
        envelope = json.loads(await request.body())
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid request body")

    if not verify_sns_signature(envelope):
        raise HTTPException(403, "Invalid SNS signature")

    msg_type = envelope.get("Type")
    if msg_type == "SubscriptionConfirmation":
        confirm_subscription(envelope["SubscribeURL"])
        return {"status": "subscribed"}
    if msg_type != "Notification":
        return {"status": "ignored", "type": msg_type}

    try:
        message = json.loads(envelope["Message"])
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(400, "Invalid SNS message payload")

    phone = message.get("originationNumber", "")
    text = (message.get("messageBody") or "").strip().upper()

    member = (await db.execute(select(Member).where(Member.phone == phone))).scalar_one_or_none()
    if member is None:
        return {"status": "no_matching_member"}

    if text in STOP_KEYWORDS:
        member.consent_sms = False
        member.consent_recorded_at = datetime.utcnow()
        # A member who opted out should not keep receiving cadence outreach.
        await end_active_enrollments_for_member(db, member.id, "opt_out")
        await log_action(
            db,
            actor_type="member",
            actor_id=member.id,
            action="sms_opt_out",
            resource_type="member",
            resource_id=member.id,
            tenant_id=member.tenant_id,
            metadata={"keyword": text},
        )
        return {"status": "opted_out"}

    if text in START_KEYWORDS:
        member.consent_sms = True
        member.consent_recorded_at = datetime.utcnow()
        await log_action(
            db,
            actor_type="member",
            actor_id=member.id,
            action="sms_opt_in",
            resource_type="member",
            resource_id=member.id,
            tenant_id=member.tenant_id,
            metadata={"keyword": text},
        )
        return {"status": "opted_in"}

    return {"status": "no_action"}
