import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.ai_service import AiService
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import (
    AiInteraction,
    CareGap,
    CaseNote,
    Conversation,
    Measure,
    Member,
    Message,
    StaffRole,
    StaffUser,
    Tenant,
    TenantMeasureConfig,
)
from app.routers.ai_assist import get_ai_service
from app.security import hash_password


class FakeBedrockClient:
    def __init__(self, text="AI DRAFT"):
        self.text = text
        self.calls = []

    async def complete(self, system, messages, model=None, max_tokens=None):
        self.calls.append({"system": system, "messages": messages})
        return {"text": self.text, "usage": {"input_tokens": 5, "output_tokens": 9}}


def _install_fake_ai(text="AI DRAFT") -> FakeBedrockClient:
    fake = FakeBedrockClient(text)
    app.dependency_overrides[get_ai_service] = lambda: AiService(client=fake, model="fake-model")
    return fake


async def _make_super_admin():
    email = f"super-{uuid.uuid4().hex[:8]}@example.com"
    async with SessionLocal() as db:
        db.add(
            StaffUser(
                tenant_id=None,
                email=email,
                password_hash=hash_password("pw-123456"),
                role=StaffRole.super_admin.value,
                name="Super",
            )
        )
        await db.commit()
    return email, "pw-123456"


async def _login(client, email, password):
    res = await client.post("/api/auth/staff/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def _auth(token):
    return {"authorization": f"Bearer {token}"}


async def _tenant(client) -> tuple[str, str]:
    """Returns (payer_admin_token, tenant_id)."""
    se, sp = await _make_super_admin()
    sa = await _login(client, se, sp)
    slug = f"ai-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "AI Test Plan",
            "enabled_measures": ["mental_health"],
            "first_admin_email": admin_email,
            "first_admin_password": "admin-pw-123",
        },
        headers=_auth(sa),
    )
    assert res.status_code == 200, res.text
    async with SessionLocal() as db:
        tid = (await db.execute(select(Tenant.id).where(Tenant.slug == slug))).scalar_one()
    pa = await _login(client, admin_email, "admin-pw-123")
    return pa, tid


async def _member_with_thread(tenant_id: str) -> tuple[str, str]:
    """Create a member + conversation with one inbound message. Returns
    (member_id, conversation_id)."""
    async with SessionLocal() as db:
        m = Member(
            tenant_id=tenant_id,
            external_member_id=f"ext-{uuid.uuid4().hex[:6]}",
            first_name="Test",
            last_name="Member",
            date_of_birth="1980-01-01",
            sex="F",
            alias="M-1234",
        )
        db.add(m)
        await db.flush()
        c = Conversation(tenant_id=tenant_id, member_id=m.id)
        db.add(c)
        await db.flush()
        db.add(
            Message(
                conversation_id=c.id,
                direction="inbound",
                channel="web",
                body="Hi, I got your reminder but I'm not sure what to do next.",
            )
        )
        await db.commit()
        return m.id, c.id


@pytest.fixture(autouse=True)
def _cleanup_overrides():
    yield
    app.dependency_overrides.pop(get_ai_service, None)


@pytest.mark.asyncio
async def test_composer_returns_draft_and_does_not_send(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    pa, tid = await _tenant(client)
    member_id, conv_id = await _member_with_thread(tid)
    _install_fake_ai("Thanks for the reply — let's get your screening scheduled.")

    async with SessionLocal() as db:
        before = await db.scalar(
            select(func.count()).select_from(Message).where(Message.conversation_id == conv_id)
        )

    res = await client.post(f"/api/conversations/{conv_id}/ai-draft", headers=_auth(pa))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["draft"].startswith("Thanks for the reply")
    assert body["interaction_id"]

    async with SessionLocal() as db:
        after = await db.scalar(
            select(func.count()).select_from(Message).where(Message.conversation_id == conv_id)
        )
        interaction = await db.get(AiInteraction, body["interaction_id"])
    assert after == before  # the draft endpoint never sends a message
    assert interaction.surface == "composer"
    assert interaction.tenant_id == tid


@pytest.mark.asyncio
async def test_composer_503_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", False)
    pa, tid = await _tenant(client)
    _, conv_id = await _member_with_thread(tid)
    _install_fake_ai()
    res = await client.post(f"/api/conversations/{conv_id}/ai-draft", headers=_auth(pa))
    assert res.status_code == 503


@pytest.mark.asyncio
async def test_composer_tenant_scoped(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    pa_a, tid_a = await _tenant(client)
    pa_b, tid_b = await _tenant(client)
    _, conv_a = await _member_with_thread(tid_a)
    _install_fake_ai()
    # Tenant B's admin cannot draft against tenant A's conversation.
    res = await client.post(f"/api/conversations/{conv_a}/ai-draft", headers=_auth(pa_b))
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_summary_reads_case_and_logs(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    pa, tid = await _tenant(client)
    member_id, _ = await _member_with_thread(tid)
    async with SessionLocal() as db:
        gap = CareGap(tenant_id=tid, member_id=member_id, measure_code="mental_health", period="2026")
        db.add(gap)
        await db.flush()
        db.add(
            CaseNote(
                care_gap_id=gap.id,
                author_id=(await db.execute(select(StaffUser.id).limit(1))).scalar_one(),
                note="Left voicemail; member to call back.",
                note_type="contact",
            )
        )
        await db.commit()
    _install_fake_ai("Member has an open mental_health gap; one contact attempt so far.")

    res = await client.post(f"/api/members/{member_id}/ai-summary", headers=_auth(pa))
    assert res.status_code == 200, res.text
    assert "mental_health" in res.json()["summary"]
    async with SessionLocal() as db:
        interaction = await db.get(AiInteraction, res.json()["interaction_id"])
    assert interaction.surface == "summary"


@pytest.mark.asyncio
async def test_outreach_draft_admin_only(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    pa, tid = await _tenant(client)
    _install_fake_ai("Reminder: your depression screening takes 2 minutes — tap to start.")
    res = await client.post(
        "/api/sequences/ai-draft-step",
        json={"measure_code": "mental_health", "intent": "second nudge, friendly", "channel": "sms"},
        headers=_auth(pa),
    )
    assert res.status_code == 200, res.text
    assert res.json()["draft"]
    async with SessionLocal() as db:
        interaction = await db.get(AiInteraction, res.json()["interaction_id"])
    assert interaction.surface == "outreach"


@pytest.mark.asyncio
async def test_outcome_updates_interaction(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    pa, tid = await _tenant(client)
    _, conv_id = await _member_with_thread(tid)
    _install_fake_ai("draft")
    draft = (await client.post(f"/api/conversations/{conv_id}/ai-draft", headers=_auth(pa))).json()
    iid = draft["interaction_id"]

    # Bad outcome rejected.
    bad = await client.post(
        f"/api/ai-interactions/{iid}/outcome", json={"outcome": "generated"}, headers=_auth(pa)
    )
    assert bad.status_code == 422

    ok = await client.post(
        f"/api/ai-interactions/{iid}/outcome", json={"outcome": "edited"}, headers=_auth(pa)
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["outcome"] == "edited"
    async with SessionLocal() as db:
        interaction = await db.get(AiInteraction, iid)
    assert interaction.outcome == "edited"
