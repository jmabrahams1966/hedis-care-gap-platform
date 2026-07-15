# Secure Messaging / Live Chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **PREREQUISITE #0.** GitHub is behind production — implement in the real source on `JMA-MBP-2026` after reconciling (`demo/RECONCILE_AND_HARDEN.md`). Paths/models below are from an older clone; confirm each against the real source. Reuses `outreach_service` (notifications), the inbound SMS webhook (`routers/webhooks.py`), member magic-link auth, Feature B's `SafetyPlan`/`EscalationStep`, and `AuditLog`. `Message.body` is PHI → encrypted per the deployed pattern; **never send a body over SMS/email** (notification only); every message + escalation audited; tenant-scoped RBAC.

**Goal:** Async unified-thread secure messaging (web + SMS notify/relay + email notify) between care team and members, with an always-on crisis auto-escalation and business-hours routing.

**Architecture:** `Conversation`/`Message` tables; a staff send service (web message + non-PHI notification); member endpoints via magic-link; inbound-SMS routing into the thread; a `crisis_scan` that auto-replies + raises a Feature B safety flag; a staff inbox + member message center + a case-workspace Messages panel.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, pytest; React 18 + TS + Vite.

**Reference spec:** `docs/superpowers/specs/2026-07-15-secure-messaging-design.md`

---

## Phase 1 — Models + staff messaging

### Task 1: `Conversation` + `Message` models + migration

**Files:** Modify `backend/app/models.py`; create migration.

- [ ] **Step 1: Models**

```python
class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), unique=True, index=True)
    assigned_staff_id: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    status: Mapped[str] = mapped_column(default="open")     # open|snoozed|closed
    crisis_flag: Mapped[bool] = mapped_column(default=False)
    last_message_at: Mapped[datetime | None] = mapped_column(nullable=True)
    staff_unread: Mapped[bool] = mapped_column(default=False)
    member_unread: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    direction: Mapped[str]                                  # inbound|outbound
    channel: Mapped[str]                                    # web|sms|email
    sender_staff_id: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    body: Mapped[str] = mapped_column()                     # PHI — encrypted column type
    delivery_status: Mapped[str | None] = mapped_column(nullable=True)
    crisis_flag: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
```

- [ ] **Step 2: Migration** (two new tables). Apply/downgrade/upgrade. **Commit**

```bash
git add backend/app/models.py backend/migrations/versions/
git commit -m "feat(msg): conversations + messages tables"
```

### Task 2: Staff send service + inbox/thread endpoints

**Files:** Create `backend/app/messaging_service.py` (send helper) + `backend/app/routers/conversations.py`; register in `main.py`; Test `backend/tests/test_messaging_staff.py`.

- [ ] **Step 1: Failing tests** —
  - `POST /api/conversations/{id}/messages` creates an outbound `Message(channel=web)`, sets `member_unread=True`, `last_message_at`, and calls a notification send (mock `outreach_service`) with a **non-PHI** body containing a magic-link (assert the member's message body is NOT in the SMS/email text).
  - `GET /api/conversations?filter=safety` lists crisis-flagged first.
  - Cross-tenant 404.

- [ ] **Step 2: Run — FAIL.** `cd backend && ./.venv/bin/python -m pytest tests/test_messaging_staff.py -v`

- [ ] **Step 3: Implement**

```python
# messaging_service.py
NOTIFY_TEMPLATE = "New secure message from your care team — tap to view: {link}"

async def send_staff_message(db, conversation, staff, body: str):
    msg = Message(conversation_id=conversation.id, direction="outbound", channel="web",
                  sender_staff_id=staff.id, body=body)
    db.add(msg)
    conversation.member_unread = True
    conversation.last_message_at = datetime.now(UTC)
    # non-PHI notification with a magic link to the secure center
    member = await db.get(Member, conversation.member_id)
    link = f"{settings.app_base_url}/messages?token=..."   # reuse magic-token issuance
    if member.consent_sms and member.phone:
        await send_sms(member.phone, NOTIFY_TEMPLATE.format(link=link))
    elif member.consent_email and member.email:
        await send_email(member.email, "New secure message", NOTIFY_TEMPLATE.format(link=link))
    await log_action(db, actor_type="staff", actor_id=staff.id, action="message_sent",
                     tenant_id=conversation.tenant_id)
    await db.commit()
    return msg
```
Then the router: inbox list (filters), thread get, send (calls the service), assign, close. Role `care_manager+`, tenant-scoped.

- [ ] **Step 4: Run — PASS.** Full suite. **Commit**

```bash
git add backend/app/messaging_service.py backend/app/routers/conversations.py backend/app/main.py backend/tests/test_messaging_staff.py
git commit -m "feat(msg): staff send (web + non-PHI notification) + inbox/thread endpoints"
```

---

## Phase 2 — Member + inbound + crisis

### Task 3: Member conversation endpoints (magic-link)

**Files:** Add member routes (in `conversations.py` or `routers/auth.py` member area); Test `backend/tests/test_messaging_member.py`.

- [ ] **Step 1: Failing tests** — an authenticated member `GET /api/member/conversation` returns their thread (auto-creates the Conversation on first access) and clears `member_unread`; `POST /api/member/conversation/messages` appends an inbound web `Message`, sets `staff_unread=True`. A member can only see their own conversation.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** using the existing member session dependency (magic-link JWT). Auto-create Conversation if none.
- [ ] **Step 4: Run — PASS.** **Commit.**

### Task 4: Inbound SMS routing

**Files:** Modify `backend/app/routers/webhooks.py` (the inbound SMS handler currently does STOP/START only); Test extend `backend/tests/test_webhooks.py`.

- [ ] **Step 1: Failing test** — a signed inbound SMS that is NOT STOP/START, from a known member's phone, appends an inbound `Message(channel=sms)` to that member's conversation and sets `staff_unread=True`. (STOP/START still behave as before.)
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — after the STOP/START branch, resolve the member by phone (tenant-scoped), get/create their conversation, append the inbound message, then call the crisis + hours logic (Task 5).
- [ ] **Step 4: Run — PASS.** Full suite. **Commit.**

### Task 5: Crisis scan + auto-reply + safety escalation + business-hours ack

**Files:** Create `backend/app/crisis.py` (`crisis_scan`, `ESCALATION_KEYWORDS`); wire into the inbound path (Task 4) and the member POST (Task 3); Test `backend/tests/test_crisis.py`.

- [ ] **Step 1: Failing tests** —
  - `crisis_scan("i want to end it")` → True; benign text → False.
  - An inbound message that trips the scan: sets `Message.crisis_flag` + `Conversation.crisis_flag`, sends an immediate 988 auto-reply (mock send; assert sent regardless of business hours), and raises a member safety flag that ties into Feature B (assert a safety `CareGap`/`EscalationStep` state + `AuditLog`).
  - An after-hours non-crisis inbound triggers the auto-acknowledge template; an in-hours one does not.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** `crisis.py` with a conservative keyword/phrase list (flag: needs clinical sign-off), the auto-reply (988 text — safe on any channel), the safety-flag hook (reuse Feature B escalation), and a `within_business_hours(tenant, now)` helper for the after-hours ack.
- [ ] **Step 4: Run — PASS.** Full suite. **Commit.**

---

## Phase 3 — Frontend

### Task 6: Staff inbox

**Files:** Create `frontend/src/pages/care-manager/Inbox.tsx` (+ `messaging.ts` client/types); add nav + route.

- [ ] **Step 1** — `messaging.ts`: `Conversation`/`Message` types + client fns.
- [ ] **Step 2** — `Inbox.tsx`: conversation list (filters: unread / mine / unassigned / safety-first, crisis pinned + red), thread view, composer (send), assign/close. Poll or refetch on send.
- [ ] **Step 3** — Type-check + browser verify: send a message, see it in the thread; a crisis-flagged conversation pins to top. **Commit.**

### Task 7: Member secure message center + case-workspace Messages panel

**Files:** Create `frontend/src/pages/member/MessageCenter.tsx` (member app, behind magic-link) + a `Messages` panel in the Feature B `CaseDetail`.

- [ ] **Step 1** — `MessageCenter.tsx`: the member's thread + reply composer; opened from the notification magic-link.
- [ ] **Step 2** — `CaseDetail` gains a Messages panel showing the same conversation in context (reuses the staff thread component).
- [ ] **Step 3** — Type-check + browser verify the end-to-end loop (staff send → member notification link → member reply → staff inbox). **Commit.**

---

## Self-review checklist (done)
- **Spec coverage:** conversation/message model (T1), staff send + non-PHI notification + inbox (T2), member endpoints (T3), inbound SMS routing (T4), crisis scan + auto-reply + safety escalation + business-hours (T5), staff inbox (T6), member center + case panel (T7). HIPAA "no PHI over SMS/email" asserted in T2's test. Email-inbound + websockets explicitly out of scope per spec.
- **Placeholders:** none unresolved; the crisis keyword list is flagged as needing clinical sign-off (shared with Feature B), not silently finalized.
- **Type consistency:** `direction` (`inbound|outbound`), `channel` (`web|sms|email`), `status` (`open|snoozed|closed`), and `crisis_flag` used identically across model, service, endpoints, and frontend types.
