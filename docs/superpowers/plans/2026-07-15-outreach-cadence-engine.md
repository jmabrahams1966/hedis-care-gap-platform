# Outreach Cadence Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **PREREQUISITE #0.** GitHub is behind production — implement in the real source on `JMA-MBP-2026` after reconciling (`demo/RECONCILE_AND_HARDEN.md`). Paths/models below are from an older clone; confirm each against the real source. Reuse `app/outreach_service.py`, `OutreachAttempt`, the `run_outreach_cron.py` job, and the STOP/START consent webhook. All new tables carry `tenant_id`, are gated to `payer_admin`+ (config) / `care_manager`+ (enrollment control), and every mutating call writes `log_action(...)`.

**Goal:** A configurable multi-step outreach cadence engine — reusable sequences (offset + channel + template per step) assigned per measure, incl. an ongoing recurring weekly MH check-in a care manager controls — driven by the existing daily cron.

**Architecture:** Three new tables (`OutreachSequence`, `SequenceStep`, `SequenceEnrollment`) + a `sequence_id` on `TenantMeasureConfig` + response fields on `OutreachAttempt`. A `cadence_service` evaluates due enrollments and sends via `outreach_service`; the daily cron calls it; auto-enroll on gap open; care-manager pause/end endpoints; a response-analytics endpoint; an admin sequence-builder UI.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, pytest + httpx.ASGITransport; React 18 + TS + Vite.

**Reference spec:** `docs/superpowers/specs/2026-07-15-outreach-cadence-engine-design.md`

---

## Phase 1 — Model + engine + cron

### Task 1: Models + migration

**Files:** Modify `backend/app/models.py`; create Alembic migration.

- [ ] **Step 1: Add models**

```python
class OutreachSequence(Base):
    __tablename__ = "outreach_sequences"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)  # NULL = platform template
    name: Mapped[str]
    is_default: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

class SequenceStep(Base):
    __tablename__ = "sequence_steps"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    sequence_id: Mapped[str] = mapped_column(ForeignKey("outreach_sequences.id"), index=True)
    order: Mapped[int]
    offset_days: Mapped[int]
    channel: Mapped[str]                # sms|email|member_preferred
    template_key: Mapped[str]
    recurring: Mapped[bool] = mapped_column(default=False)
    repeat_interval_days: Mapped[int | None] = mapped_column(nullable=True)
    __table_args__ = (UniqueConstraint("sequence_id", "order", name="uq_seq_step_order"),)

class SequenceEnrollment(Base):
    __tablename__ = "sequence_enrollments"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    care_gap_id: Mapped[str | None] = mapped_column(ForeignKey("care_gaps.id"), nullable=True)
    sequence_id: Mapped[str] = mapped_column(ForeignKey("outreach_sequences.id"))
    status: Mapped[str] = mapped_column(default="active")   # active|paused|ended
    current_step_order: Mapped[int] = mapped_column(default=0)
    next_send_at: Mapped[date]
    ended_by: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    __table_args__ = (Index("ix_enroll_due", "status", "next_send_at"),)
```
Also add to `TenantMeasureConfig`: `sequence_id: Mapped[str | None] = mapped_column(ForeignKey("outreach_sequences.id"), nullable=True)`.

- [ ] **Step 2: Migration** — `./.venv/bin/alembic revision --autogenerate -m "cadence engine tables"`. New tables need no batch; the `TenantMeasureConfig` ALTER uses `op.batch_alter_table` (SQLite). Apply/downgrade/upgrade to verify.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models.py backend/migrations/versions/
git commit -m "feat(cadence): sequence/step/enrollment tables + measure sequence_id"
```

### Task 2: `cadence_service.process_due()` engine

**Files:** Create `backend/app/cadence_service.py`; Test `backend/tests/test_cadence_engine.py`.

- [ ] **Step 1: Failing test** — an active enrollment due today sends one attempt and advances; a recurring step reschedules `+repeat_interval_days` and stays on the step; a finite sequence ends after its last step; a second run same-day sends nothing.

```python
# backend/tests/test_cadence_engine.py
import pytest
from datetime import date
from app.cadence_service import process_due
# fixtures build a sequence [Day0 sms, +3d email] and a recurring [↻7d] variant,
# enroll a member with next_send_at=today, then assert OutreachAttempt count,
# enrollment.current_step_order / next_send_at / status transitions, and idempotency.
```

- [ ] **Step 2: Run — Expected FAIL.** `cd backend && ./.venv/bin/python -m pytest tests/test_cadence_engine.py -v`

- [ ] **Step 3: Implement**

```python
# backend/app/cadence_service.py
from datetime import date, timedelta
from sqlalchemy import select
from .models import SequenceEnrollment, SequenceStep, OutreachAttempt, Member, TenantSettings  # confirm names
from .outreach_service import send_outreach  # reuse the shared send helper (confirm signature)

async def process_due(db, today: date | None = None):
    today = today or date.today()
    enrolls = (await db.execute(
        select(SequenceEnrollment).where(SequenceEnrollment.status == "active",
                                         SequenceEnrollment.next_send_at <= today)
    )).scalars().all()
    for e in enrolls:
        # idempotency: skip if an attempt already logged for this enrollment today
        already = (await db.execute(
            select(OutreachAttempt).where(OutreachAttempt.member_id == e.member_id,
                                          OutreachAttempt.created_at >= today))).first()
        step = (await db.execute(select(SequenceStep).where(
            SequenceStep.sequence_id == e.sequence_id,
            SequenceStep.order == e.current_step_order))).scalar_one_or_none()
        if step is None:
            e.status, e.ended_reason = "ended", "completed"; continue
        member = await db.get(Member, e.member_id)
        if not already and _consent_ok(member, step.channel) and _within_quiet_hours(today):
            await send_outreach(db, member, step.channel, step.template_key)  # writes OutreachAttempt
        if step.recurring:
            e.next_send_at = today + timedelta(days=step.repeat_interval_days)
        else:
            nxt = (await db.execute(select(SequenceStep).where(
                SequenceStep.sequence_id == e.sequence_id,
                SequenceStep.order == e.current_step_order + 1))).scalar_one_or_none()
            if nxt is None:
                e.status, e.ended_reason = "ended", "completed"
            else:
                e.current_step_order = nxt.order
                e.next_send_at = today + timedelta(days=nxt.offset_days)
    await db.commit()
```
Add helpers `_consent_ok(member, channel)` (checks `consent_sms`/`consent_email`, resolves `member_preferred`) and `_within_quiet_hours(today)` (tenant window; stub to always-true in tests via a settings fixture).

- [ ] **Step 4: Run — Expected PASS.** Full suite. **Commit**

```bash
git add backend/app/cadence_service.py backend/tests/test_cadence_engine.py
git commit -m "feat(cadence): process_due engine (send/advance/recur, idempotent)"
```

### Task 3: Auto-enroll on gap open + cron wiring

**Files:** Modify `backend/app/routers/members.py` (the `_open_care_gaps_for_member/dependent` helpers) to create an enrollment; modify `backend/app/scripts/run_outreach_cron.py` (or add `run_cadence_cron.py`) to call `process_due`. Test `backend/tests/test_autoenroll.py`.

- [ ] **Step 1: Failing test** — opening a care gap for a measure with an assigned sequence creates one `active` enrollment at `current_step_order = first step`, `next_send_at = today + first offset`; a measure with no sequence creates none.

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** — in the gap-open helper, look up `TenantMeasureConfig.sequence_id` (fallback: platform default sequence for the measure); if present, insert a `SequenceEnrollment`. In the cron entrypoint, `await process_due(db)` after the existing outreach step.

- [ ] **Step 4: Run — PASS.** Full suite. **Commit**

```bash
git add backend/app/routers/members.py backend/app/scripts/ backend/tests/test_autoenroll.py
git commit -m "feat(cadence): auto-enroll on gap open; run process_due in the daily cron"
```

---

## Phase 2 — Lifecycle & stop conditions

### Task 4: Enrollment endpoints + stop-on-close/opt-out

**Files:** Create `backend/app/routers/enrollments.py`; register in `main.py`; modify the gap-close path and the STOP webhook to end enrollments. Test `backend/tests/test_enrollment_lifecycle.py`.

- [ ] **Step 1: Failing tests** —
  - `GET /api/members/{id}/enrollments` lists active enrollments.
  - `POST /api/enrollments/{id}/pause` → `status=paused` (engine skips paused); `POST /api/enrollments/{id}/end` → `status=ended`, `ended_by`, audit row.
  - Closing a care gap (numerator met / mark closed) ends its gap-scoped enrollment.
  - A STOP webhook (existing) that flips consent also ends the member's active enrollments with `ended_reason="opt_out"`.
  - Cross-tenant access 404s.

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** endpoints + hook the close path (`care_gaps.py`) and the STOP handler (`webhooks.py`) to end enrollments; audit each.

- [ ] **Step 4: Run — PASS.** Full suite. **Commit**

```bash
git add backend/app/routers/enrollments.py backend/app/routers/care_gaps.py backend/app/routers/webhooks.py backend/app/main.py backend/tests/test_enrollment_lifecycle.py
git commit -m "feat(cadence): enrollment pause/end + stop on gap-close and opt-out"
```

---

## Phase 3 — Response analytics

### Task 5: Response tracking + `GET /api/reports/outreach`

**Files:** Modify `models.py` (`OutreachAttempt.responded_at`, `response_type`) + migration; the member verify/screening path to mark the latest attempt responded; `reports.py` for the aggregate. Test `backend/tests/test_outreach_report.py`.

- [ ] **Step 1: Failing test** — after a member verifies within the window following an attempt, that attempt has `responded_at`; `GET /api/reports/outreach?period=2026` returns per-sequence/step/channel `{sent, responded, response_rate}`.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — add columns (batch migration); in `auth.py` verify (or screening submit), set `responded_at=now, response_type=...` on the member's most recent unresponded attempt within N days; add the report aggregation.
- [ ] **Step 4: Run — PASS.** Full suite. **Commit**

```bash
git commit -am "feat(cadence): outreach response tracking + GET /api/reports/outreach"
```

---

## Phase 4 — Sequences API + frontend

### Task 6: Sequences CRUD + assign-per-measure API

**Files:** Create `backend/app/routers/sequences.py`; register in `main.py`; extend the measures-config endpoint to set `sequence_id`. Test `backend/tests/test_sequences.py`.

- [ ] **Step 1: Failing tests** — create a sequence with steps; edit steps; assign to a measure via `PATCH /api/tenants/measures/{code}` (`sequence_id`); role gating (payer_admin/super_admin); tenant isolation; platform templates readable by all tenants (copy-on-edit).
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** `sequences.py` (`GET/POST /api/sequences`, `GET/PUT/DELETE /api/sequences/{id}` with nested steps) + the assignment patch; audit writes.
- [ ] **Step 4: Run — PASS.** Full suite. **Commit.**

### Task 7: Sequence-builder UI + assignment

**Files:** Create `frontend/src/pages/admin/SequenceBuilder.tsx` (+ `sequences.ts` client/types); wire into the admin measures/config nav. Reference mock `.superpowers/brainstorm/2279-1784112459/content/sequence-builder.html`.

- [ ] **Step 1** — `sequences.ts`: `Sequence`/`Step` types + CRUD client fns.
- [ ] **Step 2** — `SequenceBuilder.tsx`: name + measure assignment + ordered step rows (offset, channel pills, template select, recurring toggle + interval), "+ Add step", and a preview timeline; save via the API.
- [ ] **Step 3** — Type-check (`npx tsc --noEmit`) + browser verify: build the DSF sequence, assign it, confirm a new gap enrolls (check via the enrollments endpoint). **Commit.**

### Task 8: Care-manager enrollment control + outreach analytics view

**Files:** Modify the Feature B case workspace (`CaseDetail`) to show active enrollments with pause/end + a "Next outreach" line; create `frontend/src/pages/admin/OutreachAnalytics.tsx`.

- [ ] **Step 1** — In the case sidebar, list the member's enrollments (from `GET /api/members/{id}/enrollments`) with pause/end buttons; show `next_send_at`/channel.
- [ ] **Step 2** — `OutreachAnalytics.tsx`: table of `GET /api/reports/outreach` (sent/responded/rate by sequence·step·channel).
- [ ] **Step 3** — Type-check + browser verify pause/end stops sends; analytics renders. **Commit.**

---

## Self-review checklist (done)
- **Spec coverage:** sequences/steps/enrollments (T1), engine send/advance/recur + idempotency (T2), auto-enroll + cron (T3), pause/end + stop-on-close/opt-out (T4), response tracking + report (T5), sequences CRUD + assignment (T6), builder UI (T7), care-manager control + analytics (T8). Quiet-hours/consent handled in T2 helpers. Both open questions (default sequence content; quiet-hours tz) carried from spec §10 — flagged, not silently resolved.
- **Placeholders:** none unresolved; `send_outreach`/`_consent_ok`/`_within_quiet_hours` signatures named and to be confirmed against the real `outreach_service`.
- **Type consistency:** `channel` vocab (`sms|email|member_preferred`), `status` (`active|paused|ended`), and `SequenceEnrollment` field names identical across model, engine (T2), lifecycle (T4), and frontend (T7–8).
