# Design — Outreach Cadence Engine (Feature C1)

**Date:** 2026-07-15
**Product:** cogai-payor / HEDIS Care Gap Platform
**Status:** Approved design, pending implementation plan
**Implement in:** the real source on `JMA-MBP-2026` (GitHub is behind prod — reconcile first).

## 1. Purpose

Replace the single daily follow-up nudge with a configurable, multi-step outreach
**cadence engine**: reusable sequences (offset + channel + template per step) assigned
per measure, including an ongoing recurring **weekly mental-health check-in** that a care
manager controls. Improves engagement and directly serves the "more frequent MH checks"
ask. Pharmacy/medication-adherence (Feature C2) is deferred; this design leaves a seam
(a self-report "medication check-in" is just another cadence type/template).

## 2. Goals & non-goals

**Goals**
- Reusable multi-step sequences; assign one per measure per tenant; platform defaults.
- Recurring weekly MH check-in, care-manager-controlled (start/pause/end).
- Reuse `outreach_service`, `OutreachAttempt`, the daily cron, and STOP/START consent.
- Response analytics (sent / delivered / responded, by sequence·step·channel).

**Non-goals (this spec)**
- Pharmacy/PDC data + medication-adherence measure logic (Feature C2, separate spec).
- Conditional/branching rules engine (v-next).
- Per-member best-time-of-day optimization (v1 = tenant-level quiet-hours only).

## 3. Data model

New tables (tenant-scoped; audited via `log_action`):
- **`OutreachSequence`** — `id, tenant_id (NULL = platform template), name, is_default,
  created_by, created_at`.
- **`SequenceStep`** — `id, sequence_id, order, offset_days, channel
  (sms|email|member_preferred), template_key, recurring (bool), repeat_interval_days (NULL
  unless recurring)`. Unique `(sequence_id, order)`.
- **`SequenceEnrollment`** (runtime) — `id, tenant_id, member_id,
  care_gap_id (NULL for standalone MH), sequence_id, status (active|paused|ended),
  current_step_order, next_send_at, ended_by (NULL), ended_reason (NULL), created_at`.
  Index `(status, next_send_at)`; partial-unique on an active enrollment per
  `(member_id, sequence_id, care_gap_id)` to prevent double-enroll.

Column adds:
- **`TenantMeasureConfig.sequence_id`** (nullable FK) — the sequence a measure uses for the tenant.
- **`OutreachAttempt.responded_at` (nullable), `response_type` (nullable str)** — for analytics.

Templates: `template_key` maps to the existing notification template functions
(`app/notifications/*`); no free-text PHI stored on steps.

## 4. Engine (extend the existing daily cron)

For each `active` enrollment with `next_send_at <= today`:
1. Load member; check `consent_sms`/`consent_email` for the resolved channel and the
   tenant **quiet-hours** window; if blocked, skip (retry next day).
2. Resolve channel: step channel, or `member.preferred_channel` when `member_preferred`.
3. Send via `outreach_service` using `template_key`; write an `OutreachAttempt`.
4. If the step is `recurring`: `next_send_at += repeat_interval_days` (stay on the step).
   Else: advance `current_step_order`; if a next step exists, `next_send_at = today + its
   offset_days`; if none, `status = ended`, `ended_reason = "completed"`.
Idempotent per day (a sent attempt for the enrollment today ⇒ skip).

## 5. Enrollment lifecycle & stop conditions

- **Auto-enroll** on care-gap open into the measure's assigned sequence (or the platform
  default if the tenant hasn't assigned one).
- **MH weekly:** a DSF **follow-up/safety** additionally creates a standalone
  (`care_gap_id = NULL`) enrollment in the recurring weekly-MH sequence.
- **Ends when:** gap closed / numerator met (gap-scoped enrollments) · member STOP/opt-out
  (existing webhook flips consent → engine skips, and enrollment marked `ended`) · finite
  sequence completes · **care manager pauses/ends** (recurring MH).
- Every state change audited.

## 6. Channel, consent, best-time

- Respect `consent_sms` / `consent_email`; a channel with no consent is skipped (and if the
  step is single-channel with no consent, the step is skipped, not retried forever).
- **Best-time v1:** tenant-level quiet-hours (`send_window_start/end` on `Tenant`, default
  08:00–20:00). Per-member timezone/preferred-time deferred (needs a member tz field).

## 7. Response analytics

- `OutreachAttempt.responded_at` set when the member acts within a window (magic-link verify
  / screening completion) after a touch; `response_type` records what.
- **`GET /api/reports/outreach?period=…`** → sent / delivered / responded and response-rate,
  grouped by sequence, step, and channel. A small "Outreach" analytics view; can feed a
  Feature A dashboard tile later (not in A's v1 KPI set).

## 8. API

- Sequences (payer_admin/super_admin): `GET/POST /api/sequences`, `GET/PUT/DELETE
  /api/sequences/{id}` (+ nested step edits), and assign via `PATCH
  /api/tenants/measures/{code}` setting `sequence_id`.
- Enrollments (care_manager+): `GET /api/members/{id}/enrollments`,
  `POST /api/enrollments/{id}/pause`, `POST /api/enrollments/{id}/end`
  (both audited; care-manager control of the recurring MH check-in).
- Analytics: `GET /api/reports/outreach`.

## 9. Frontend

- **Admin sequence builder** (extends admin measures/config): create/edit sequences —
  ordered steps (offset, channel pills, template, recurring toggle + interval) + a preview
  timeline; assign a sequence per measure. (Approved mock:
  `.superpowers/brainstorm/2279-1784112459/content/sequence-builder.html`.)
- **Care-manager control** (in the Feature B case workspace): a member's active
  enrollments with pause/end; a "Next outreach: <date> via <channel>" line on the case.
- **Outreach analytics** view (response metrics).

## 10. Open questions

- **Q1 — default sequence content per measure** (offsets/channels/templates, esp. the MH
  weekly cadence): needs a light clinical/ops sign-off before seeding.
- **Q2 — quiet-hours timezone:** v1 tenant-level; member-level needs a `Member.timezone`
  field (deferred).

## 11. Sequencing

1. Models + migration + engine service + cron (auto-enroll gap-scoped sequences; send/advance/recur).
2. Enrollment lifecycle endpoints (pause/end) + stop conditions + STOP/opt-out integration.
3. Response tracking (`OutreachAttempt` fields) + `GET /api/reports/outreach`.
4. Frontend: sequence builder + assignment; care-manager control; analytics view.

## 12. Success criteria

- A tenant admin builds "Depression — screen & engage" (Day0 SMS · +3d Email · +4d SMS ·
  ↻7d preferred) and assigns it to DSF.
- Opening a DSF gap enrolls the member; the cron sends Day-0, then the sequence advances on
  schedule; closing the gap ends the enrollment.
- A safety flag starts the recurring weekly enrollment; a care manager ends it from the case;
  no further sends occur.
- `GET /api/reports/outreach` shows per-step sent/responded counts.
