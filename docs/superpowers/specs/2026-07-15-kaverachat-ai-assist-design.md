# Design — KaveraChat AI Assist (Feature E)

**Date:** 2026-07-15
**Product:** cogai-payor / HEDIS Care Gap Platform
**Status:** Approved design, pending implementation plan
**Implement in:** the real source on `JMA-MBP-2026` (GitHub is behind prod — reconcile first).
**Naming:** "KaveraChat" (per canonical naming, "Cora" was dropped).

## 1. Purpose

A staff-facing, human-in-the-loop AI assist layer over the existing surfaces: draft replies,
summarize cases, triage risk, and draft outreach copy — all reviewed/edited by a human before
anything reaches a member. Reuses the Bedrock Claude already in the stack (in-VPC, BAA-covered).

## 2. Goals & non-goals

**Goals**
- One shared `ai_service` core + four thin surfaces (composer draft, note summary, risk triage,
  outreach-template draft).
- Two hard invariants: **human-in-the-loop gate** (AI output is always a draft/suggestion) and
  **AI never replaces the deterministic safety net** (D's keyword crisis scan + 988 auto-reply
  still fire; AI triage is additive only).
- HIPAA: all model calls in-VPC via Bedrock; audit every interaction; PHI-minimized storage.

**Non-goals (this spec)**
- **Member-facing AI companion** (AI conversing directly with members) — deferred; separate,
  heavily-guardrailed effort with clinical/legal review.
- Autonomous actions — nothing AI produces is sent/persisted to a member automatically.
- Fine-tuning / custom models — prompt-only over the configured Bedrock Claude.

## 3. Architecture

**`ai_service` (core)** wraps the app's existing Bedrock Claude client (do not author a new LLM
integration — reuse the one the app already uses). Injectable client so tests mock it. For each
surface: build a prompt (template + context) → call Claude → return completion + telemetry →
write an `AiInteraction` audit row. Four surfaces are thin callers of this core.

## 4. Invariants (safety)

1. **Human-gate:** every output populates a field/panel a human must act on; no auto-send/persist to member.
2. **Deterministic safety net stays primary:** D's keyword crisis scan + immediate 988 reply run
   regardless; AI risk triage augments, never gates, that path.
3. **Untrusted input:** member-supplied text is data, not instructions — system prompts say so
   (prompt-injection defense).
4. **Clinical guardrails:** system prompts forbid direct-to-patient medical advice, require flagging
   uncertainty, defer to the clinician.

## 5. Data model

- **`AiInteraction`** — `id, tenant_id, surface (composer|summary|triage|outreach), actor_staff_id,
  member_id (nullable), model, prompt_tokens, completion_tokens, latency_ms,
  outcome (accepted|edited|discarded|generated), created_at`. Store references/hashes, not raw PHI
  prompt dumps; encrypt any retained sensitive text. No other new domain tables.

## 6. Surfaces (each = prompt template + endpoint + UI affordance)

1. **Composer draft (D):** `POST /api/conversations/{id}/ai-draft` → draft reply from thread + case
   context → fills the composer (editable). Records `outcome` when sent/edited/discarded.
2. **Note summary (B):** `POST /api/members/{id}/ai-summary` → synthesis of notes + screenings +
   trajectory → read-only panel.
3. **Risk triage (D/screenings):** `assess_risk(text, context)` → `{level, rationale}` surfaced to
   staff (a chip); augments the keyword scan; never auto-acts.
4. **Outreach template draft (C1):** `POST /api/sequences/ai-draft-step` → drafts step copy for admin review.

## 7. Model & cost

Reuse the configured Bedrock model. Tiering: **Haiku-class for high-volume risk triage**,
**Sonnet-class for drafting/summarization**. Per-tenant rate/cost caps; log tokens per interaction.
**Confirm exact model IDs/params against the Claude-API reference and the real config at build**
(models move fast; the other-Mac config is source of truth).

## 8. API

- `POST /api/conversations/{id}/ai-draft` (care_manager+)
- `POST /api/members/{id}/ai-summary` (care_manager+)
- Risk triage: internal, called on inbound message ingest (D) and screening submit; result attached
  to the message/case, not a standalone endpoint (a `GET` may expose it for the UI chip).
- `POST /api/sequences/ai-draft-step` (payer_admin+)
- `POST /api/ai-interactions/{id}/outcome` — record accepted|edited|discarded for quality tracking.

## 9. Frontend affordances

- D composer: **"✨ Draft reply"** → editable draft. B workspace: **"Summarize case"** → panel.
- D thread: staff-only **risk chip** with rationale on hover. C1 builder: **"Draft copy"** on a step.
- Each draft/summary shows a subtle "AI-generated — review before use" label.

## 10. Reuse & seams

Reuses the existing Bedrock Claude client, Feature D (composer/triage), Feature B (notes/summary),
C1 (templates), `AuditLog`, RBAC. The deferred **member-facing companion** would attach at D's
member surface later, behind heavy guardrails + separate clinical/legal review.

## 11. Open questions

1. **Model tiering/IDs** — confirm against the Claude-API reference + real config at build.
2. **Prompt/output retention** — PHI-minimization policy needs compliance sign-off.
3. **Risk-triage eval** — accuracy validation before it's trusted; keyword scan remains the hard net.

## 12. Sequencing

1. `ai_service` core (injectable Bedrock client) + `AiInteraction` + migration.
2. Composer draft (D) + outcome tracking.
3. Note summary (B).
4. Risk triage (D/screenings) — additive to the keyword scan.
5. Outreach template draft (C1).
6. Frontend affordances + AI-generated labels.

## 13. Success criteria

- "Draft reply" in the D inbox returns a context-aware draft in the composer; sending records
  `outcome=edited|accepted`; nothing sends without the human clicking send.
- "Summarize case" returns a faithful synthesis; risk triage adds a staff-only signal without ever
  altering the deterministic 988 path.
- Every AI call writes an `AiInteraction`; no raw PHI prompt is persisted beyond policy; all calls
  go to Bedrock in-VPC (no external LLM).
