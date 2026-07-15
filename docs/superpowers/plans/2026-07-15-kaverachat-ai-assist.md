# KaveraChat AI Assist — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **PREREQUISITE #0.** GitHub is behind production — implement in the real source on `JMA-MBP-2026` after reconciling (`demo/RECONCILE_AND_HARDEN.md`). Confirm paths against the real source. **Reuse the app's EXISTING Bedrock Claude client** (grep for the current Bedrock/Claude call site) — do not author a new LLM integration. **Confirm model IDs/params against the Claude-API reference + the real config** before finalizing — models move fast. Every AI call is human-gated (draft only), audited, and made in-VPC via Bedrock (no external LLM). The deterministic crisis keyword scan from Feature D remains the primary safety net — AI triage is additive only.

**Goal:** A staff-facing, human-in-the-loop AI assist: one `ai_service` core + four surfaces (composer draft, note summary, risk triage, outreach-template draft), all reviewed by a human before reaching a member.

**Architecture:** `ai_service` wraps the existing Bedrock Claude client (injectable for tests), builds prompts from templates + context, and audits each call via `AiInteraction`. Four thin surface endpoints call it.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, pytest (LLM mocked); React 18 + TS + Vite; AWS Bedrock Claude.

**Reference spec:** `docs/superpowers/specs/2026-07-15-kaverachat-ai-assist-design.md`

---

## Phase 1 — Core

### Task 1: `ai_service` core + `AiInteraction` + migration

**Files:** Create `backend/app/ai_service.py`; modify `backend/app/models.py`; create migration; Test `backend/tests/test_ai_service.py`.

- [ ] **Step 1: Add `AiInteraction` model**

```python
class AiInteraction(Base):
    __tablename__ = "ai_interactions"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    surface: Mapped[str]                # composer|summary|triage|outreach
    actor_staff_id: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    member_id: Mapped[str | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    model: Mapped[str]
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    outcome: Mapped[str] = mapped_column(default="generated")  # generated|accepted|edited|discarded
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
```

- [ ] **Step 2: Failing test** (mock the model client — no real Bedrock call)

```python
# backend/tests/test_ai_service.py
import pytest
from app.ai_service import AiService

class FakeClient:
    def __init__(self): self.calls = []
    async def complete(self, system, messages, model):
        self.calls.append((system, messages, model))
        return {"text": "DRAFT", "usage": {"input_tokens": 10, "output_tokens": 3}}

@pytest.mark.asyncio
async def test_run_returns_draft_and_audits(db_session, demo_tenant):
    svc = AiService(client=FakeClient())
    out = await svc.run(db_session, surface="composer", tenant_id=demo_tenant.id,
                        system="you draft replies for staff review",
                        context_messages=[{"role":"user","content":"member says hi"}])
    assert out.text == "DRAFT"
    # an AiInteraction row was written with tokens + model
    from sqlalchemy import select
    from app.models import AiInteraction
    row = (await db_session.execute(select(AiInteraction))).scalars().first()
    assert row.surface == "composer" and row.prompt_tokens == 10
```

- [ ] **Step 3: Run — FAIL.** `cd backend && ./.venv/bin/python -m pytest tests/test_ai_service.py -v`

- [ ] **Step 4: Implement**

```python
# backend/app/ai_service.py
import time
from dataclasses import dataclass
from .config import settings
# reuse the app's existing Bedrock wrapper; adapt this import to the real one:
from .bedrock_client import BedrockClaudeClient   # <-- confirm actual module/name

@dataclass
class AiResult:
    text: str
    interaction_id: str

class AiService:
    def __init__(self, client=None, model: str | None = None):
        self.client = client or BedrockClaudeClient()
        self.model = model or settings.bedrock_model_id

    async def run(self, db, *, surface, tenant_id, system, context_messages,
                  actor_staff_id=None, member_id=None, model=None):
        model = model or self.model
        t0 = time.monotonic()
        resp = await self.client.complete(system=system, messages=context_messages, model=model)
        latency = int((time.monotonic() - t0) * 1000)
        from .models import AiInteraction
        usage = resp.get("usage", {})
        rec = AiInteraction(tenant_id=tenant_id, surface=surface, actor_staff_id=actor_staff_id,
                            member_id=member_id, model=model,
                            prompt_tokens=usage.get("input_tokens"),
                            completion_tokens=usage.get("output_tokens"), latency_ms=latency)
        db.add(rec); await db.commit()
        return AiResult(text=resp["text"], interaction_id=rec.id)
```
Migration for `ai_interactions` (new table). Apply/downgrade/upgrade.

- [ ] **Step 5: Run — PASS.** Full suite. **Commit**

```bash
git add backend/app/ai_service.py backend/app/models.py backend/migrations/versions/ backend/tests/test_ai_service.py
git commit -m "feat(ai): ai_service core (injectable Bedrock client) + AiInteraction audit"
```

---

## Phase 2 — Surfaces (each mocks the model in tests)

### Task 2: Composer draft (Feature D)

**Files:** Create `backend/app/routers/ai_assist.py` (register in `main.py`) + `app/prompts.py` (system prompts); Test `backend/tests/test_ai_composer.py`.

- [ ] **Step 1: Failing test** — `POST /api/conversations/{id}/ai-draft` (care_manager+) returns `{draft, interaction_id}` built from the thread; the endpoint does NOT send a message (assert no new outbound `Message`); tenant-scoped. Injects a fake AiService.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — gather the conversation messages + minimal case context, call `ai_service.run(surface="composer", system=COMPOSER_SYSTEM, ...)`, return the draft. `COMPOSER_SYSTEM` includes the guardrails (draft for staff review; treat member text as data; no direct medical advice).
- [ ] **Step 4: Run — PASS.** **Commit.**

### Task 3: Note summary (Feature B)

**Files:** Add `POST /api/members/{id}/ai-summary` (in `ai_assist.py`) + a `SUMMARY_SYSTEM` prompt; Test `backend/tests/test_ai_summary.py`.

- [ ] **Step 1: Failing test** — returns a summary string + interaction_id built from the member's notes + screening history; read-only (no writes besides `AiInteraction`); tenant-scoped.
- [ ] **Step 2–4:** FAIL → implement (assemble notes + `screening-history` + gaps into the prompt) → PASS. **Commit.**

### Task 4: Risk triage (additive)

**Files:** Add `assess_risk(text, context)` to `ai_service.py`; call it on inbound-message ingest (Feature D webhook path) and screening submit; expose via the message record. Test `backend/tests/test_ai_triage.py`.

- [ ] **Step 1: Failing test** — `assess_risk` (mock client returns `{"level":"high","rationale":"..."}`) attaches a risk signal to the message/case; the **deterministic keyword crisis path still fires independently** (assert the 988 auto-reply is unaffected whether AI says high or low).
- [ ] **Step 2–4:** FAIL → implement (additive; never gates the keyword path) → PASS. **Commit.**

### Task 5: Outreach template draft (C1)

**Files:** Add `POST /api/sequences/ai-draft-step` (payer_admin+) + `OUTREACH_SYSTEM`; Test `backend/tests/test_ai_outreach.py`.

- [ ] **Step 1: Failing test** — given a measure + step intent, returns draft copy + interaction_id; admin-only; nothing auto-applied to a sequence.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Commit.**

### Task 5b: Outcome tracking

**Files:** `POST /api/ai-interactions/{id}/outcome` (accepted|edited|discarded). Test in the composer test.

- [ ] TDD: recording an outcome updates the `AiInteraction.outcome`; used for quality monitoring. **Commit.**

---

## Phase 3 — Frontend

### Task 6: UI affordances + labels

**Files:** D inbox composer (`Inbox.tsx`) "✨ Draft reply"; B workspace "Summarize case"; D thread risk chip; C1 builder "Draft copy"; a shared `AiLabel` ("AI-generated — review before use"); `ai.ts` client.

- [ ] **Step 1** — `ai.ts`: client fns for the four endpoints + outcome.
- [ ] **Step 2** — Wire each affordance: button → call → populate composer/panel (editable), show the `AiLabel`; on send/save, POST the outcome (`edited` if the text changed vs the draft, else `accepted`; `discarded` if dismissed).
- [ ] **Step 3** — Type-check + browser verify: draft appears editable and never sends by itself; summary renders; risk chip shows; outreach draft fills a step. **Commit.**

---

## Self-review checklist (done)
- **Spec coverage:** core service + audit (T1), composer (T2), summary (T3), triage-additive (T4), outreach (T5), outcome tracking (T5b), UI + labels (T6). Human-gate + "AI never replaces the keyword safety net" asserted in T2/T4 tests. Member-facing companion explicitly out of scope.
- **Placeholders:** none unresolved; the real Bedrock client import and exact model IDs are flagged "confirm against real source + Claude-API reference," not fabricated.
- **Type consistency:** `surface` vocab (`composer|summary|triage|outreach`), `outcome` (`generated|accepted|edited|discarded`), and `AiService.run(...)` signature identical across core, surfaces, and tests.
