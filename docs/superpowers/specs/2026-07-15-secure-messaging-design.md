# Design — Secure Messaging / Live Chat (Feature D)

**Date:** 2026-07-15
**Product:** cogai-payor / HEDIS Care Gap Platform
**Status:** Approved design, pending implementation plan
**Implement in:** the real source on `JMA-MBP-2026` (GitHub is behind prod — reconcile first).

## 1. Purpose

Two-way secure messaging between the payor care team and (high-risk) members: one unified
conversation per member spanning web, SMS, and email, worked from a care-team inbox and the
Feature B case workspace, with an always-on crisis safety net. Async store-and-forward (no
websockets in v1); real-time web is a clean later seam.

## 2. Goals & non-goals

**Goals**
- Unified `Conversation`/`Message` thread per member; care-team inbox + member secure web center.
- HIPAA-safe channel handling: PHI only in the authenticated web view; SMS/email are notify-and-relay.
- Auto crisis detection → immediate 988 reply + safety flag + escalation + team alert.
- Business-hours routing with after-hours auto-acknowledge.

**Non-goals (this spec)**
- Real-time websocket chat (v-next; thread model unchanged).
- Inbound **email** parsing (SES receive) — email is notify-only in v1.
- AI drafting/triage — that's the Feature E seam (crisis-scan + composer).

## 3. Architecture — async, unified thread

One `Conversation` per (tenant, member); all channels append to it.
- **Outbound (staff→member):** web message → member's secure center. SMS/email → **non-PHI
  notification** ("New secure message from your care team — tap to view: <magic-link>"); body
  never crosses SMS/email.
- **Inbound (member→team):** web reply (authed) → `Message`. **Inbound SMS** captured by the
  existing webhook (extended beyond STOP/START) → appended. Email inbound deferred.

## 4. Data model

- **`Conversation`** — `id, tenant_id, member_id, assigned_staff_id (nullable),
  status (open|snoozed|closed), crisis_flag, last_message_at, staff_unread (bool),
  member_unread (bool), created_at`. Index `(tenant_id, status, last_message_at)`.
- **`Message`** — `id, conversation_id, direction (inbound|outbound), channel (web|sms|email),
  sender_staff_id (nullable), body (PHI → encrypted), delivery_status (nullable),
  crisis_flag (bool), created_at`.
Reuses: `Member`, `StaffUser`, consent flags, `AuditLog`, and Feature B's
`SafetyPlan`/`EscalationStep` for crisis handling.

## 5. Crisis escalation

Every **inbound** message runs `crisis_scan(text) -> bool` (keyword/phrase list — shares the
Feature B escalation-list open question). On a hit:
1. Auto-reply immediately (any hour) with 988 + Crisis Text Line (safe on any channel, no PHI).
2. Raise a **safety flag** on the member → Feature B escalation workflow + pinned in the queue.
3. Set `Conversation.crisis_flag`, alert assigned/on-call staff.
4. Human review always follows. All steps audited.

## 6. Business-hours routing

Tenant `business_hours` config (window + timezone). In-hours inbound → normal inbox. After-hours
→ **auto-acknowledge** ("We got your message; the team replies during business hours. Emergency?
Call 988/911."). Crisis-flagged messages get the immediate crisis reply regardless of hour.

## 7. Consent, HIPAA, audit

- Notify only on a consented channel (`consent_sms`/`consent_email` + STOP/START); the web center
  is always available to an authenticated member.
- **No PHI over SMS/email**; message bodies encrypted at rest (PHI). Every message + escalation
  audited. Tenant-scoped RBAC (care_manager+ for staff endpoints; member scoped to own conversation).

## 8. API

**Staff (care_manager+):**
- `GET /api/conversations?filter=unread|mine|unassigned|safety` — inbox (safety-first).
- `GET /api/conversations/{id}` — thread.
- `POST /api/conversations/{id}/messages` — send (web message + notification via `outreach_service`).
- `POST /api/conversations/{id}/assign`, `POST /api/conversations/{id}/close`.

**Member (magic-link session):**
- `GET /api/member/conversation`, `POST /api/member/conversation/messages`.

**Inbound SMS:** extend the existing webhook — non-STOP/START texts route into the member's
conversation and run the crisis scan + business-hours logic.

## 9. Frontend

- **Staff Inbox** — conversation list (unread/mine/unassigned, safety pinned) + thread + composer.
- **Messages panel** in the Feature B case workspace (same thread, in context).
- **Member secure message center** in the member web app (behind magic-link).

## 10. Reuse & seams

`outreach_service` send + `OutreachAttempt` (notifications), magic-link auth, Feature B safety
workflow, C1 send helpers. **Real-time (websocket) web chat** is a v-next seam (thread model
unchanged). The **crisis-scan + composer** is exactly where **Feature E (Cora/AI)** plugs in to
draft/triage.

## 11. Open questions

1. **Crisis keyword list** — clinical sign-off (shares Feature B's escalation list); v1 = conservative
   list + mandatory human follow-up.
2. **Email inbound** — deferred (notify-only in v1); confirm.
3. **Real-time** — deferred to v-next.
4. **Member-initiated SMS may contain PHI** by the member's own choice — stored in the thread; staff
   replies still go via secure link, never PHI over SMS. Confirm this handling is acceptable.

## 12. Sequencing

1. `Conversation`/`Message` models + migration.
2. Staff send (web + notification) + inbox/thread endpoints.
3. Member conversation endpoints (magic-link).
4. Inbound SMS routing + crisis scan + auto-reply + safety-flag escalation + business-hours ack.
5. Frontend: staff inbox, member center, case-workspace Messages panel.

## 13. Success criteria

- Staff sends a message → member gets a non-PHI SMS/email notification with a magic-link; the body
  appears only in the authenticated web center; member replies and it lands in the staff inbox.
- An inbound SMS with crisis language triggers an immediate 988 auto-reply (even after-hours), raises
  a safety flag that pins the member in the queue, and alerts the team.
- No message body is ever sent over SMS/email; all bodies encrypted; every message audited.
