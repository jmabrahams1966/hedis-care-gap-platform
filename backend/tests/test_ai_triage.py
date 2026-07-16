import json
import uuid

import pytest
from sqlalchemy import select

from app.ai_service import AiService
from app.config import settings
from app.db import SessionLocal
from app.messaging_service import record_inbound_message
from app.models import AiInteraction, Conversation, Member, Message, Tenant


class FakeTriageClient:
    """Returns a canned triage JSON. `raises` simulates a Bedrock failure."""

    def __init__(self, level="high", raises=False):
        self.level = level
        self.raises = raises

    async def complete(self, system, messages, model=None, max_tokens=None):
        if self.raises:
            raise RuntimeError("bedrock unavailable")
        return {
            "text": json.dumps({"level": self.level, "rationale": "advisory rationale"}),
            "usage": {"input_tokens": 3, "output_tokens": 4},
        }


async def _member_and_conversation() -> tuple[str, str, str]:
    """Returns (tenant_id, member_id, conversation_id)."""
    async with SessionLocal() as db:
        t = Tenant(slug=f"tri-{uuid.uuid4().hex[:8]}", name="Triage Plan")
        db.add(t)
        await db.flush()
        m = Member(
            tenant_id=t.id,
            external_member_id=f"ext-{uuid.uuid4().hex[:6]}",
            first_name="T",
            last_name="M",
            date_of_birth="1980-01-01",
            sex="F",
            phone="",
            alias="M-9",
        )
        db.add(m)
        await db.flush()
        c = Conversation(tenant_id=t.id, member_id=m.id)
        db.add(c)
        await db.commit()
        return t.id, m.id, c.id


@pytest.mark.asyncio
async def test_assess_risk_disabled_returns_none(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", False)
    tid, mid, _ = await _member_and_conversation()
    svc = AiService(client=FakeTriageClient(level="high"))
    async with SessionLocal() as db:
        assert await svc.assess_risk(db, text="I feel awful", tenant_id=tid, member_id=mid) is None


@pytest.mark.asyncio
async def test_assess_risk_enabled_returns_signal_and_logs(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    tid, mid, _ = await _member_and_conversation()
    svc = AiService(client=FakeTriageClient(level="high"), model="fake-model")
    async with SessionLocal() as db:
        signal = await svc.assess_risk(db, text="I feel awful", tenant_id=tid, member_id=mid)
        await db.commit()
    assert signal["level"] == "high"
    assert signal["interaction_id"]
    async with SessionLocal() as db:
        row = await db.get(AiInteraction, signal["interaction_id"])
    assert row.surface == "triage"


@pytest.mark.asyncio
async def test_assess_risk_swallows_errors(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    tid, mid, _ = await _member_and_conversation()
    svc = AiService(client=FakeTriageClient(raises=True))
    async with SessionLocal() as db:
        # A Bedrock failure must not propagate — triage is best-effort.
        assert await svc.assess_risk(db, text="hello", tenant_id=tid, member_id=mid) is None


@pytest.mark.asyncio
async def test_crisis_path_independent_of_ai_signal(client, monkeypatch):
    """The deterministic 988 auto-reply must fire on a crisis keyword regardless
    of what AI triage says — even when AI reports 'low' or is unavailable."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    tid, mid, cid = await _member_and_conversation()

    async with SessionLocal() as db:
        conv = await db.get(Conversation, cid)
        member = await db.get(Member, mid)
        # AI says "low" — the deterministic keyword scan must still escalate.
        low_ai = AiService(client=FakeTriageClient(level="low"))
        msg, outcome = await record_inbound_message(
            db, conv, member, "I want to kill myself", channel="web", ai=low_ai
        )
        await db.commit()
        conv_id = conv.id

    assert outcome == "crisis"  # deterministic path fired
    async with SessionLocal() as db:
        msgs = (
            await db.execute(select(Message).where(Message.conversation_id == conv_id))
        ).scalars().all()
        # inbound flagged crisis + an outbound 988 auto-reply exists
        assert any(m.direction == "inbound" and m.crisis_flag for m in msgs)
        assert any(m.direction == "outbound" and m.crisis_flag for m in msgs)
        # AI signal is additive: attached to the inbound message but did not gate anything
        inbound = next(m for m in msgs if m.direction == "inbound")
        assert inbound.ai_risk_level == "low"


@pytest.mark.asyncio
async def test_inbound_ai_failure_does_not_break_ingest(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    tid, mid, cid = await _member_and_conversation()
    async with SessionLocal() as db:
        conv = await db.get(Conversation, cid)
        member = await db.get(Member, mid)
        broken = AiService(client=FakeTriageClient(raises=True))
        msg, outcome = await record_inbound_message(
            db, conv, member, "just a normal question", channel="web", ai=broken
        )
        await db.commit()
        msg_id = msg.id
    async with SessionLocal() as db:
        stored = await db.get(Message, msg_id)
    assert stored is not None  # message persisted despite AI failure
    assert stored.ai_risk_level is None
