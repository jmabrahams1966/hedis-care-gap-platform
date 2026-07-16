"""KaveraChat AI assist core (Feature E).

One entry point — `AiService.run()` — that every AI surface (composer draft, note
summary, risk triage, outreach draft) calls. It owns the cross-cutting concerns
so the surfaces stay thin:

  * the feature gate (`settings.ai_enabled`) — off → `AiDisabledError` → 503,
    so the whole feature ships dormant until the Bedrock IAM grant is applied;
  * the Bedrock call (via `BedrockClaudeClient`, in-VPC only);
  * the `AiInteraction` audit row (surface, staff, model, tokens, latency);
  * a stable `AiResult(text, interaction_id)` the caller returns to the operator.

Every AI output is a *draft*: it is returned to a human who accepts, edits, or
discards it (recorded later via the outcome endpoint). Nothing here writes a note,
message, or status — the surfaces do that only after the human acts.
"""

import logging
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from .bedrock_client import BedrockClaudeClient
from .config import settings
from .models import AiInteraction

logger = logging.getLogger("ai.service")


class AiDisabledError(RuntimeError):
    """Raised when an AI surface is invoked with settings.ai_enabled=False.
    Routers translate this to HTTP 503 so the feature is inert until enabled."""


@dataclass
class AiResult:
    text: str
    interaction_id: str


class AiService:
    def __init__(self, client: BedrockClaudeClient | None = None, model: str | None = None) -> None:
        self.client = client or BedrockClaudeClient()
        self.model = model or settings.bedrock_model_id

    async def run(
        self,
        db: AsyncSession,
        *,
        surface: str,
        tenant_id: str,
        system: str,
        context_messages: list[dict],
        actor_staff_id: str | None = None,
        member_id: str | None = None,
        model: str | None = None,
    ) -> AiResult:
        if not settings.ai_enabled:
            raise AiDisabledError("AI assist is not enabled")

        chosen = model or self.model
        started = time.monotonic()
        result = await self.client.complete(system, context_messages, model=chosen)
        latency_ms = int((time.monotonic() - started) * 1000)

        usage = result.get("usage", {})
        interaction = AiInteraction(
            tenant_id=tenant_id,
            surface=surface,
            actor_staff_id=actor_staff_id,
            member_id=member_id,
            model=chosen,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            latency_ms=latency_ms,
            outcome="generated",
        )
        db.add(interaction)
        await db.commit()
        await db.refresh(interaction)

        return AiResult(text=result.get("text", ""), interaction_id=interaction.id)
