import uuid

import pytest
from sqlalchemy import func, select

from app.ai_service import AiDisabledError, AiResult, AiService
from app.config import settings
from app.db import SessionLocal
from app.models import AiInteraction, Tenant


class FakeBedrockClient:
    """Records the last call and returns a canned completion — no AWS."""

    def __init__(self, text: str = "draft text") -> None:
        self.text = text
        self.calls: list[dict] = []

    async def complete(self, system, messages, model=None, max_tokens=None):
        self.calls.append({"system": system, "messages": messages, "model": model})
        return {"text": self.text, "usage": {"input_tokens": 11, "output_tokens": 7}}


async def _tenant() -> str:
    async with SessionLocal() as db:
        t = Tenant(slug=f"ai-{uuid.uuid4().hex[:8]}", name="AI Test Plan")
        db.add(t)
        await db.commit()
        return t.id


@pytest.mark.asyncio
async def test_run_disabled_raises_and_writes_nothing(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", False)
    tenant_id = await _tenant()
    svc = AiService(client=FakeBedrockClient())

    async with SessionLocal() as db:
        with pytest.raises(AiDisabledError):
            await svc.run(
                db,
                surface="summary",
                tenant_id=tenant_id,
                system="s",
                context_messages=[{"role": "user", "content": "hi"}],
            )
        count = await db.scalar(select(func.count()).select_from(AiInteraction))
    assert count == 0


@pytest.mark.asyncio
async def test_run_enabled_returns_result_and_logs_interaction(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    tenant_id = await _tenant()
    fake = FakeBedrockClient(text="Suggested note draft")
    svc = AiService(client=fake, model="test-model-id")

    async with SessionLocal() as db:
        result = await svc.run(
            db,
            surface="composer",
            tenant_id=tenant_id,
            system="You are a drafting assistant.",
            context_messages=[{"role": "user", "content": "draft a reply"}],
            actor_staff_id=None,
            member_id=None,
        )

    assert isinstance(result, AiResult)
    assert result.text == "Suggested note draft"
    assert result.interaction_id

    async with SessionLocal() as db:
        row = await db.get(AiInteraction, result.interaction_id)
    assert row is not None
    assert row.surface == "composer"
    assert row.tenant_id == tenant_id
    assert row.model == "test-model-id"
    assert row.prompt_tokens == 11
    assert row.completion_tokens == 7
    assert row.latency_ms is not None and row.latency_ms >= 0
    assert row.outcome == "generated"
    assert fake.calls[0]["model"] == "test-model-id"
