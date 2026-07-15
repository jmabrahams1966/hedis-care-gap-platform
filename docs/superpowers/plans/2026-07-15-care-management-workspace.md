# Care-Management Workspace — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **PREREQUISITE #0 — read before starting.** GitHub is **behind production**. Implement in the real deployed source on `JMA-MBP-2026` after reconciling GitHub↔prod (`demo/RECONCILE_AND_HARDEN.md`). File paths/models below are verified against an **older clone** — confirm each against the real source and adapt drifted names. Build Feature A first (`2026-07-15-quality-overview-dashboard.md`); this plan assumes its shared helpers may exist.

> **PHI + audit pattern (applies to every new table/column below).** Free-text clinical fields (note bodies, care-plan text, safety-plan sections) are PHI: declare them using the **same encrypted-column type the deployed code already uses for `Member` PII** (driven by `PII_ENCRYPTION_KEY` / `KMS_KEY_ARN`) — grep the real `models.py` for how Member PHI columns are typed and copy that. Every create/update endpoint writes an `AuditLog` entry via the existing `log_action(...)` helper. All new tables carry `tenant_id` and are gated to `care_manager`+ within the tenant; verify the member/gap belongs to the caller's tenant on every request.

**Goal:** Turn the case-detail page into a care-management workspace: per-member PHQ-9/GAD-7 trend, typed free-text clinical notes, care plan, tasks/SLA, and a safety plan + escalation checklist with audit.

**Architecture:** Four new tenant-scoped tables (`CareTask`, `CarePlanGoal`, `SafetyPlan`, `EscalationStep`) + a `note_type` column on the existing `CaseNote`, each with a small CRUD router; a read endpoint that reshapes `ScreeningSubmission.instrument_scores` into a trend series; and a restructured `CaseDetail` React page composed of focused components.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, pytest + httpx.ASGITransport; React 18 + TS + Vite, TanStack Query.

**Reference spec:** `docs/superpowers/specs/2026-07-15-care-management-workspace-design.md`

---

## Phase 1 — MH trend + typed notes (highest demo value, lowest risk)

### Task 1: `CaseNote.note_type`

**Files:** Modify `backend/app/models.py`, `backend/app/schemas.py`, the notes router; create migration; Test `backend/tests/test_note_type.py`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_note_type.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_note_saves_and_returns_type(cm_token, open_case_gap_id):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(f"/api/care-gaps/{open_case_gap_id}/notes",
                         json={"body": "called member", "note_type": "safety_check"},
                         headers={"Authorization": f"Bearer {cm_token}"})
    assert r.status_code in (200, 201)
    assert r.json()["note_type"] == "safety_check"
```

- [ ] **Step 2: Run — Expected FAIL** (`note_type` unknown / not returned).
Run: `cd backend && ./.venv/bin/python -m pytest tests/test_note_type.py -v`

- [ ] **Step 3: Implement**

```python
# models.py — CaseNote
note_type: Mapped[str] = mapped_column(default="other")  # contact|assessment|safety_check|care_coordination|other
# schemas.py — the note-create model gains:
note_type: str = "other"
# router — pass body.note_type into CaseNote(...) and include it in the response dict.
```
Add a module constant for validation:
```python
NOTE_TYPES = {"contact", "assessment", "safety_check", "care_coordination", "other"}
# in the handler: if body.note_type not in NOTE_TYPES: raise HTTPException(422, "bad note_type")
```

- [ ] **Step 4: Migration** — `./.venv/bin/alembic revision --autogenerate -m "add case_note.note_type"`; the ALTER on an existing table must use `op.batch_alter_table(...)` (SQLite convention in this repo). Apply + downgrade + upgrade to verify.

- [ ] **Step 5: Run test — PASS**, then full suite. **Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/app/routers/ backend/migrations/versions/ backend/tests/test_note_type.py
git commit -m "feat(notes): typed free-text clinical notes (CaseNote.note_type)"
```

### Task 2: Screening-history endpoint (for the trend chart)

**Files:** Modify `backend/app/routers/members.py`; Test `backend/tests/test_screening_history.py`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_screening_history.py
@pytest.mark.asyncio
async def test_screening_history_returns_scores_over_time(cm_token, member_with_two_dsf_submissions):
    mid = member_with_two_dsf_submissions
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/api/members/{mid}/screening-history?measure=mental_health",
                        headers={"Authorization": f"Bearer {cm_token}"})
    assert r.status_code == 200
    pts = r.json()
    assert len(pts) == 2
    assert set(pts[0]) >= {"date", "phq9", "gad7"}
    assert pts[0]["date"] <= pts[1]["date"]  # chronological
```

- [ ] **Step 2: Run — Expected FAIL.**

- [ ] **Step 3: Implement**

```python
# members.py
@router.get("/{member_id}/screening-history")
async def screening_history(member_id: str, measure: str,
                            staff = Depends(require_role(StaffRole.care_manager.value,
                                     StaffRole.payer_admin.value, StaffRole.super_admin.value)),
                            db: AsyncSession = Depends(get_db)):
    member = await db.get(Member, member_id)
    if member is None or (staff.tenant_id and member.tenant_id != staff.tenant_id):
        raise HTTPException(404, "Member not found")
    rows = (await db.execute(
        select(ScreeningSubmission)
        .where(ScreeningSubmission.member_id == member_id,
               ScreeningSubmission.measure_code == measure)
        .order_by(ScreeningSubmission.created_at)
    )).scalars().all()
    out = []
    for s in rows:
        sc = s.instrument_scores or {}
        out.append({"date": s.created_at.date().isoformat(),
                    "phq9": (sc.get("phq9") or {}).get("score"),
                    "gad7": (sc.get("gad7") or {}).get("score")})
    return out
```
(Confirm the `instrument_scores` shape against the real scoring module — the clone stores `{"phq9": {...,"score":N}, "gad7": {...}}`.)

- [ ] **Step 4: Run — PASS.** Full suite. **Commit**

```bash
git add backend/app/routers/members.py backend/tests/test_screening_history.py
git commit -m "feat(mh): GET /api/members/{id}/screening-history for the trend chart"
```

### Task 3: CaseDetail restructure + MhTrendChart + typed notes UI

**Files:** Modify `frontend/src/pages/care-manager/CaseDetail.tsx`; create `frontend/src/pages/care-manager/MhTrendChart.tsx`, `ClinicalNotes.tsx`. Reference approved mock `.superpowers/brainstorm/87955-1784076232/content/case-workspace.html`.

- [ ] **Step 1: `MhTrendChart.tsx`** — fetches `screening-history`, renders a small inline-SVG two-line chart (PHQ-9 + GAD-7) with a legend. Props: `memberId`. Handles empty history (show "No screenings yet").

```tsx
// minimal SVG line chart; scale scores 0..27 to the viewBox height, plot phq9 + gad7.
```

- [ ] **Step 2: `ClinicalNotes.tsx`** — the existing note list + composer, plus a note-type `<select>` (the 5 types); on submit POST `{body, note_type}`; render a type badge per note. (Moves the notes JSX out of `CaseDetail` into this focused component.)

- [ ] **Step 3: Restructure `CaseDetail`** into the approved two-column workspace: main = `<MhTrendChart/>` (only for `measure_code === "mental_health"`) then `<ClinicalNotes/>` then a care-plan slot (Task 8); sidebar = existing summary+actions, then a tasks slot (Task 6), then a safety slot (Task 11). Leave the slots as empty placeholders wired in later phases.

- [ ] **Step 4: Type-check + browser verify** — `cd frontend && npx tsc --noEmit`; run the app, open a flagged MH case, confirm the trend renders and a typed note saves. **Commit**

```bash
git add frontend/src/pages/care-manager/
git commit -m "feat(workspace): restructure CaseDetail; MhTrendChart + typed ClinicalNotes"
```

---

## Phase 2 — Tasks & reminders

### Task 4: `CareTask` model + migration

**Files:** Modify `models.py`; create migration; (types are non-PHI — a task title is operational, keep plain unless it may contain PHI, then encrypt).

- [ ] **Step 1: Model**

```python
class CareTask(Base):
    __tablename__ = "care_tasks"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    care_gap_id: Mapped[str | None] = mapped_column(ForeignKey("care_gaps.id"), nullable=True)
    title: Mapped[str]
    due_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sla_hours: Mapped[int | None] = mapped_column(nullable=True)
    assignee_staff_id: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    status: Mapped[str] = mapped_column(default="open")  # open|done|cancelled
    created_by: Mapped[str] = mapped_column(ForeignKey("staff_users.id"))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

- [ ] **Step 2: Migration** (new table — no batch needed). Apply/downgrade/upgrade. **Commit.**

### Task 5: Tasks endpoints + overdue rollup

**Files:** Create `backend/app/routers/tasks.py`; register in `main.py`; Test `backend/tests/test_tasks.py`.

- [ ] **Step 1: Failing tests** — create a task; list tasks for a member; complete a task (sets `status=done`, `completed_at`); `GET /api/tasks?status=overdue` returns tasks whose `due_at < now` and `status=open`; cross-tenant access 404s.

```python
# backend/tests/test_tasks.py — 4 tests as above, each asserting status codes + audit side effects.
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** `tasks.py` with:
  - `POST /api/members/{id}/tasks` (create; default `member`-scoped, `care_gap_id` optional per spec open-question default),
  - `GET /api/members/{id}/tasks`,
  - `PATCH /api/tasks/{tid}` (complete/cancel; sets `completed_at`),
  - `GET /api/tasks?status=overdue&assignee=me` (rollup; `me` → `staff.id`).
  Each mutating call: tenant check + `log_action(...)`.

- [ ] **Step 4: Run — PASS.** Full suite. **Commit.**

### Task 6: TaskList UI + queue overdue indicator

**Files:** Create `frontend/src/pages/care-manager/TaskList.tsx`; modify `CaseDetail` (fill the tasks slot) and the queue list to show an overdue badge/filter.

- [ ] **Step 1** — `TaskList.tsx`: lists a member's tasks with due/SLA chips (overdue red, upcoming amber), an "add task" row (title + due date + optional assignee), and a complete checkbox (PATCH).
- [ ] **Step 2** — On the queue, add an "overdue tasks" indicator/filter fed by `GET /api/tasks?status=overdue` (member ids with overdue tasks). *(Dashboard KPI tile deferred — see spec B §6.)*
- [ ] **Step 3** — Type-check + browser verify a task creates, shows overdue when past due, completes. **Commit.**

---

## Phase 3 — Care plan

### Task 7: `CarePlanGoal` model + migration + endpoints

**Files:** `models.py` (+migration), `backend/app/routers/care_plan.py` (create), `main.py`; Test `backend/tests/test_care_plan.py`.

- [ ] **Step 1: Model** (goal_text + interventions_text are PHI → encrypted column type)

```python
class CarePlanGoal(Base):
    __tablename__ = "care_plan_goals"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    care_gap_id: Mapped[str | None] = mapped_column(ForeignKey("care_gaps.id"), nullable=True)
    goal_text: Mapped[str]              # PHI — encrypted column type
    interventions_text: Mapped[str]     # PHI — encrypted column type
    target_date: Mapped[date | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default="open")  # open|met|discontinued
    created_by: Mapped[str] = mapped_column(ForeignKey("staff_users.id"))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
```

- [ ] **Step 2: Failing tests** — create goal; list goals for member; patch status → met; tenant isolation. **Run — FAIL.**
- [ ] **Step 3: Implement** `care_plan.py`: `GET/POST /api/members/{id}/care-plan`, `PATCH /api/care-plan/{gid}`; tenant checks + audit; migration (new table). **Run — PASS.** **Commit.**

### Task 8: CarePlan UI

**Files:** Create `frontend/src/pages/care-manager/CarePlan.tsx`; wire into `CaseDetail` main column.

- [ ] Goal rows (goal + interventions + target date + status), "+ Goal" form, status toggle. Type-check + browser verify. **Commit.**

---

## Phase 4 — Safety plan + escalation

### Task 9: `SafetyPlan` + `EscalationStep` models + migration

**Files:** `models.py` (+migration).

- [ ] **Step 1: Models**

```python
class SafetyPlan(Base):                 # one active per member
    __tablename__ = "safety_plans"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), unique=True, index=True)
    warning_signs: Mapped[str] = mapped_column(default="")        # PHI — encrypted
    coping_strategies: Mapped[str] = mapped_column(default="")    # PHI — encrypted
    support_contacts: Mapped[str] = mapped_column(default="")     # PHI — encrypted
    means_restriction: Mapped[str] = mapped_column(default="")    # PHI — encrypted
    notes: Mapped[str] = mapped_column(default="")               # PHI — encrypted
    updated_by: Mapped[str] = mapped_column(ForeignKey("staff_users.id"))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

class EscalationStep(Base):
    __tablename__ = "escalation_steps"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    care_gap_id: Mapped[str] = mapped_column(ForeignKey("care_gaps.id"), index=True)
    step_key: Mapped[str]               # from the fixed protocol list (OPEN QUESTION — see below)
    completed: Mapped[bool] = mapped_column(default=False)
    completed_by: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    __table_args__ = (UniqueConstraint("care_gap_id", "step_key", name="uq_gap_step"),)
```

> **OPEN QUESTION (from spec B §9):** the fixed `step_key` protocol list needs **clinical sign-off** before hard-coding. Placeholder set for build/testing: `crisis_line_provided`, `outreach_completed`, `bh_warm_handoff`, `pcp_notified`. Do not ship to a real plan without sign-off (`docs/HEDIS_COMPLIANCE.md`).

- [ ] **Step 2: Migration** (two new tables). Apply/downgrade/upgrade. **Commit.**

### Task 10: Safety + escalation endpoints (audited)

**Files:** Create `backend/app/routers/safety.py`; register in `main.py`; Test `backend/tests/test_safety.py`.

- [ ] **Step 1: Failing tests** — `PUT /api/members/{id}/safety-plan` upserts and returns sections; `GET /api/care-gaps/{id}/escalation` returns the protocol steps with completion state (seeding missing steps as incomplete); `POST /api/care-gaps/{id}/escalation/{step_key}` toggles + writes an `AuditLog` row with actor + timestamp; unknown `step_key` → 422; cross-tenant → 404.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** `safety.py` with a module `ESCALATION_STEPS = [...]` (the placeholder set), upsert semantics for the plan, toggle + audit for steps. **Run — PASS.** Full suite. **Commit.**

### Task 11: SafetyPanel UI

**Files:** Create `frontend/src/pages/care-manager/SafetyPanel.tsx`; wire into `CaseDetail` sidebar, rendered **only when `safety_flag`** (prominent, red).

- [ ] Escalation checklist (checkboxes → POST toggle, showing who/when), a collapsible safety-plan editor (the five sections → PUT). Type-check + browser verify on a flagged case. **Commit.**

---

## Self-review checklist (done)
- **Spec coverage:** note_type (T1), MH trend + screening-history (T2–3), tasks + SLA + overdue rollup (T4–6), care plan (T7–8), safety plan + escalation + audit (T9–11) — every spec §4/§5/§6 item mapped.
- **Placeholders:** none unresolved; the escalation `step_key` set is explicitly flagged as a clinical-sign-off open question with a named placeholder for build/testing (matches spec B §9). The tasks member-vs-gap default is resolved to member-scoped with nullable `care_gap_id` (spec B §9).
- **Type consistency:** `note_type` values identical in `NOTE_TYPES`, model default, and the T1 test; `status` vocabularies consistent per table; `screening-history` returns `{date,phq9,gad7}` matching what `MhTrendChart` consumes; `EscalationStep.step_key` set is the single `ESCALATION_STEPS` constant used by model, endpoint, and UI.
- **PHI:** every free-text clinical column is annotated "encrypted"; every mutating endpoint notes the `log_action` audit + tenant check per the header rule.
