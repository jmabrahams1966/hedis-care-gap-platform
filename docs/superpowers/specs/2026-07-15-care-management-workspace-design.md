# Design — Care-Management Workspace (Feature B)

**Date:** 2026-07-15
**Product:** cogai-payor / HEDIS Care Gap Platform
**Status:** Approved design, pending implementation plan
**Implement in:** the real source on `JMA-MBP-2026` (GitHub is behind prod — reconcile first).

## 1. Purpose

Turn the case-detail page into a real care-management workspace, strongest for
mental-health cases: see a member's trajectory, document clinically, plan care,
track tasks, and run the safety/crisis protocol with an audit trail — all in one place.

## 2. Goals & non-goals

**Goals** — four pieces, all in v1:
1. Longitudinal PHQ-9/GAD-7 trend per member.
2. Clinical notes: free-text body + a **note type** (not fully structured templates).
3. Care plan: goals + interventions.
4. Safety & crisis: structured safety plan + escalation checklist with audit.
5. Tasks & reminders: assignable, due dates, SLA; overdue surfaced upstream.

**Non-goals (this spec)**
- Fully structured/templated note forms (deferred — free-text + type only).
- Live chat / real-time messaging (Feature D).
- Pharmacy-refill data ingestion (Feature C) — the care-plan/task can *reference* a
  refill goal, but no pharmacy integration here.

## 3. Layout (approved)

Unified scroll on case detail (no deep tabs), max-width, with safety banner under the header:
- **Main column:** PHQ-9/GAD-7 trend chart → Clinical notes (type picker + timeline) →
  Care plan (goals + interventions).
- **Sidebar:** Case summary + existing actions → Tasks & reminders (due/SLA chips) →
  Safety & crisis panel (red; shown when `safety_flag` — escalation checklist + audit note).

## 4. Data model

- **`CaseNote.note_type`** (new enum column): `contact | assessment | safety_check |
  care_coordination | other`. Body stays free-text. Default `other`.
- **`CarePlanGoal`** (new): `id, tenant_id, member_id, care_gap_id (nullable), goal_text,
  interventions_text, target_date (nullable), status (open|met|discontinued),
  created_by, created_at, updated_at`.
- **`CareTask`** (new): `id, tenant_id, member_id, care_gap_id (nullable), title,
  due_at (nullable), sla_hours (nullable), assignee_staff_id (nullable),
  status (open|done|cancelled), created_by, created_at, completed_at`.
- **`SafetyPlan`** (new, one active per member): `id, tenant_id, member_id,
  warning_signs, coping_strategies, support_contacts, means_restriction, notes,
  updated_by, updated_at`. All free-text sections.
- **`EscalationStep`** (new): `id, tenant_id, care_gap_id, step_key, completed,
  completed_by, completed_at`. `step_key` from a fixed protocol list (e.g.
  `crisis_line_provided`, `outreach_completed`, `bh_warm_handoff`, `pcp_notified`).

All new tables tenant-scoped; PHI columns use the deployed **PII-encryption pattern**
(`PII_ENCRYPTION_KEY`). Every create/update writes an `AuditLog` entry.

## 5. API (all role: care_manager+; tenant-scoped; member must belong to tenant)

- Notes: existing endpoint gains `note_type` in the body.
- `GET/POST/PATCH /api/members/{id}/care-plan` (goals CRUD).
- `GET/POST/PATCH /api/members/{id}/tasks` (+ `PATCH .../tasks/{tid}` to complete);
  `GET /api/tasks?status=overdue&assignee=me` for queue/dashboard rollups.
- `GET/PUT /api/members/{id}/safety-plan`.
- `GET /api/care-gaps/{id}/escalation` + `POST /api/care-gaps/{id}/escalation/{step_key}` (toggle, audited).
- `GET /api/members/{id}/screening-history?measure=mental_health` →
  `[{date, phq9, gad7}]` from `ScreeningSubmission.instrument_scores` (for the trend chart).

## 6. Frontend

- Restructure `CaseDetail` into the approved two-column workspace.
- New components: `MhTrendChart` (line), `ClinicalNotes` (type picker + timeline —
  upgrades current notes), `CarePlan`, `TaskList`, `SafetyPanel` (renders when flagged).
- Overdue task count from `GET /api/tasks?status=overdue` surfaces on the **queue**
  (an overdue indicator/filter). A dashboard "Follow-ups overdue" KPI tile is a
  fast-follow — it's not in Feature A's v1 KPI set (closure rate, safety, bonus,
  reached), so add it to the dashboard only if desired later.

## 7. Non-functional

- **Safety-critical UI:** the safety panel and escalation checklist must never be hidden
  behind a tab for a flagged case; render it prominently in the sidebar.
- **Audit:** escalation steps, safety-plan edits, and note creation all attributed +
  timestamped (existing `AuditLog`).
- **RBAC:** care_manager and up within the tenant; no cross-tenant access.

## 8. Sequencing

1. `note_type` + MH trend chart + screening-history endpoint (low-risk, high demo value).
2. Tasks & reminders (+ overdue rollup into queue/dashboard).
3. Care plan.
4. Safety plan + escalation checklist.

## 9. Open questions

- Fixed escalation `step_key` list — confirm the clinical protocol steps with sign-off
  (see `docs/HEDIS_COMPLIANCE.md` / clinical review) before hard-coding.
- Whether tasks are member-scoped or gap-scoped by default (spec allows both via nullable
  `care_gap_id`; UI defaults to member-scoped).

## 10. Success criteria

- On a flagged USFHP case: trend chart renders from real screening history; a typed note
  saves; a task with a due date shows and rolls up as overdue when past due; the safety
  panel shows the escalation checklist and writes audit entries on toggle.
