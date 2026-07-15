# Quality Overview Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **PREREQUISITE #0 — read before starting.** The GitHub repo is **behind production**. Implement this in the real deployed source on `JMA-MBP-2026` (which has PII encryption, audit archiving, and extra measures). Reconcile GitHub↔prod first (`demo/RECONCILE_AND_HARDEN.md`). Treat the file paths and code below as **verified against an older clone** — confirm each path/model/field name against the real source before writing, and adapt names that drifted. Do NOT implement from the stale clone.

**Goal:** Add a tenant-scoped "Quality Overview" dashboard for plan leadership: KPI strip, per-measure performance, and a safety-first priority worklist, driven by one aggregation endpoint over existing care-gap data.

**Architecture:** One new read-only backend endpoint `GET /api/reports/overview` aggregates `CareGap`/`ScreeningSubmission` data into KPIs + per-measure rows + a worklist. React renders it as `OverviewPage` (KpiStrip, MeasurePerformanceTable, PriorityWorklist, PeriodSelector). Trend, snapshots, and bonus-$ are a separate v1.1 phase at the end.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, pytest + httpx.ASGITransport; React 18 + TypeScript + Vite, TanStack Query, Axios.

**Reference the design spec:** `docs/superpowers/specs/2026-07-15-quality-overview-dashboard-design.md`

---

## Phase 1 — v1 (no trend; ships on existing data)

### Task 1: Overview aggregation endpoint

**Files:**
- Modify: `backend/app/routers/reports.py` (add `GET /overview`)
- Test: `backend/tests/test_overview.py` (create)

**Notes for the implementer:** confirm in the real source — the auth dep name (`require_role`), the `GapStatus`/`NumeratorSource` enum values, and whether `reports.py` already imports these. `super_admin` staff have `tenant_id = None`; require a `?tenant=<slug>` query param for them and resolve to the tenant id; for `payer_admin` use `staff.tenant_id` and ignore the param.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_overview.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_overview_returns_kpis_and_measures(seeded_tenant_token):
    # seeded_tenant_token: fixture returning a payer_admin JWT for a tenant with
    # a known set of care gaps (reuse the pattern in tests/test_api_flow.py).
    token = seeded_tenant_token
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/reports/overview?period=2026",
                        headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert set(body["kpis"]) >= {"gap_closure_rate", "open_safety_flags",
                                 "members_reached", "members_enrolled"}
    assert isinstance(body["measures"], list) and body["measures"]
    m = body["measures"][0]
    assert set(m) >= {"code", "name", "eligible", "completed", "rate",
                      "remaining", "source_split"}
    assert set(m["source_split"]) == {"self_report", "claims_confirmed"}
    assert isinstance(body["worklist"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_overview.py -v`
Expected: FAIL (404 / route not found).

- [ ] **Step 3: Implement the endpoint**

```python
# backend/app/routers/reports.py  (add near the existing report routes)
from sqlalchemy import select, func
from ..models import CareGap, GapStatus, NumeratorSource, Measure, Member, Tenant

@router.get("/overview")
async def quality_overview(
    period: int,
    tenant: str | None = None,
    staff = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    # resolve tenant scope
    tenant_id = staff.tenant_id
    if tenant_id is None:  # super_admin must specify
        if not tenant:
            raise HTTPException(400, "super_admin must pass ?tenant=<slug>")
        t = (await db.execute(select(Tenant).where(Tenant.slug == tenant))).scalar_one_or_none()
        if t is None:
            raise HTTPException(404, "Tenant not found")
        tenant_id = t.id

    open_states = [GapStatus.open.value, GapStatus.outreach_sent.value,
                   GapStatus.needs_follow_up.value]

    # per-measure aggregation
    gaps = (await db.execute(
        select(CareGap).where(CareGap.tenant_id == tenant_id, CareGap.period == period)
    )).scalars().all()

    by_measure: dict[str, dict] = {}
    for g in gaps:
        m = by_measure.setdefault(g.measure_code, {
            "eligible": 0, "completed": 0, "self": 0, "claims": 0})
        m["eligible"] += 1
        if g.numerator_met:
            m["completed"] += 1
        if g.numerator_source == NumeratorSource.self_report.value:
            m["self"] += 1
        elif g.numerator_source == NumeratorSource.claims_confirmed.value:
            m["claims"] += 1

    names = dict((await db.execute(select(Measure.code, Measure.hedis_measure_name))).all())
    measures = []
    for code, m in sorted(by_measure.items()):
        elig, done = m["eligible"], m["completed"]
        confirmed = m["self"] + m["claims"]
        measures.append({
            "code": code,
            "name": names.get(code, code),
            "eligible": elig,
            "completed": done,
            "rate": round(done / elig, 4) if elig else 0.0,
            "remaining": elig - done,
            "source_split": {
                "self_report": round(m["self"] / confirmed, 4) if confirmed else 0.0,
                "claims_confirmed": round(m["claims"] / confirmed, 4) if confirmed else 0.0,
            },
            "trend_points": None,  # v1.1
        })

    total_elig = sum(x["eligible"] for x in measures)
    total_done = sum(x["completed"] for x in measures)
    open_safety = sum(1 for g in gaps if g.safety_flag and g.status in open_states)
    members_reached = len({g.member_id for g in gaps})
    members_enrolled = (await db.execute(
        select(func.count(Member.id)).where(Member.tenant_id == tenant_id))).scalar_one()

    # worklist: reuse the queue's ordering (safety first). If a shared helper exists
    # in routers/care_gaps.py, call it; otherwise inline the top-N safety-first query.
    worklist_rows = sorted(
        (g for g in gaps if g.status in open_states),
        key=lambda g: (not g.safety_flag, g.status != GapStatus.needs_follow_up.value),
    )[:8]
    worklist = [{"care_gap_id": g.id, "measure_code": g.measure_code,
                 "status": g.status, "safety_flag": g.safety_flag} for g in worklist_rows]

    return {
        "period": period,
        "kpis": {
            "gap_closure_rate": round(total_done / total_elig, 4) if total_elig else 0.0,
            "open_safety_flags": open_safety,
            "bonus_at_risk": None,  # v1.1
            "members_reached": members_reached,
            "members_enrolled": members_enrolled,
        },
        "measures": measures,
        "worklist": worklist,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_overview.py -v`
Expected: PASS. Also run the full suite: `./.venv/bin/python -m pytest -q` (no regressions).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/reports.py backend/tests/test_overview.py
git commit -m "feat(reports): add GET /api/reports/overview aggregation endpoint"
```

### Task 2: `?measure=` filter for the queue (drill-down target)

**Files:**
- Modify: `backend/app/routers/care_gaps.py` (the queue list endpoint) or wherever the queue reads from — confirm in real source.
- Test: `backend/tests/test_queue_filter.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_queue_filter.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_queue_filters_by_measure(seeded_tenant_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/care-gaps?measure=mental_health",
                        headers={"Authorization": f"Bearer {seeded_tenant_token}"})
    assert r.status_code == 200
    assert all(row["measure_code"] == "mental_health" for row in r.json())
```

- [ ] **Step 2: Run it — Expected: FAIL** (filter ignored / param unknown).
Run: `cd backend && ./.venv/bin/python -m pytest tests/test_queue_filter.py -v`

- [ ] **Step 3: Add the optional filter to the queue query**

```python
# in the queue list handler signature:
measure: str | None = None,
# in the query builder, after the tenant/status filters:
if measure:
    stmt = stmt.where(CareGap.measure_code == measure)
```

- [ ] **Step 4: Run it — Expected: PASS.** Then full suite.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/care_gaps.py backend/tests/test_queue_filter.py
git commit -m "feat(queue): support ?measure= filter for dashboard drill-down"
```

### Task 3: Frontend API types + client

**Files:**
- Create: `frontend/src/lib/overview.ts` (types + fetch)
- Test: `frontend/src/lib/overview.test.ts` (if the frontend has a test runner; otherwise skip and rely on type-check)

- [ ] **Step 1: Define types + fetch fn**

```ts
// frontend/src/lib/overview.ts
import { api } from "./api";

export interface MeasureRow {
  code: string; name: string; eligible: number; completed: number;
  rate: number; remaining: number;
  source_split: { self_report: number; claims_confirmed: number };
  trend_points: number | null;
}
export interface Overview {
  period: number;
  kpis: {
    gap_closure_rate: number; open_safety_flags: number;
    bonus_at_risk: number | null; members_reached: number; members_enrolled: number;
  };
  measures: MeasureRow[];
  worklist: { care_gap_id: string; measure_code: string; status: string; safety_flag: boolean }[];
}
export const getOverview = (period: number, token?: string) =>
  api.get<Overview>(`/api/reports/overview?period=${period}`, token);
```

- [ ] **Step 2: Type-check.** Run: `cd frontend && npx tsc --noEmit` — Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/overview.ts
git commit -m "feat(overview): frontend types + client for the overview endpoint"
```

### Task 4: Presentational components

**Files:**
- Create: `frontend/src/pages/overview/KpiStrip.tsx`, `MeasurePerformanceTable.tsx`, `PriorityWorklist.tsx`, `PeriodSelector.tsx`
- Reference the approved mockup: `.superpowers/brainstorm/87955-1784076232/content/dashboard-layout-v5.html`

- [ ] **Step 1: `KpiStrip.tsx`** — renders the four KPI boxes (number on top, label under; red for safety, green for bonus). Props: `kpis: Overview["kpis"]`. Hide the bonus box when `bonus_at_risk === null`.

```tsx
// frontend/src/pages/overview/KpiStrip.tsx
import type { Overview } from "../../lib/overview";
export function KpiStrip({ kpis }: { kpis: Overview["kpis"] }) {
  const pct = (n: number) => `${Math.round(n * 100)}%`;
  return (
    <div className="kpi-grid">
      <div className="kpi"><div className="n">{pct(kpis.gap_closure_rate)}</div><div className="l">Gap-closure rate</div></div>
      <div className="kpi alert"><div className="n">{kpis.open_safety_flags}</div><div className="l">Open safety flags</div></div>
      {kpis.bonus_at_risk != null && (
        <div className="kpi money"><div className="n">${(kpis.bonus_at_risk/1e6).toFixed(1)}M</div><div className="l">Bonus at risk</div></div>
      )}
      <div className="kpi"><div className="n">{kpis.members_reached.toLocaleString()}</div>
        <div className="l">Members reached</div><div className="sub">of {kpis.members_enrolled.toLocaleString()}</div></div>
    </div>
  );
}
```

- [ ] **Step 2: `MeasurePerformanceTable.tsx`** — one row per measure with a rate bar, eligible, completed, and a self/claims split bar. Each row is a `<Link to={`/queue?measure=${code}`}>`.

```tsx
// frontend/src/pages/overview/MeasurePerformanceTable.tsx
import { Link } from "react-router-dom";
import type { MeasureRow } from "../../lib/overview";
export function MeasurePerformanceTable({ rows }: { rows: MeasureRow[] }) {
  return (
    <div className="measure-table">
      {rows.map((m) => (
        <Link key={m.code} to={`/queue?measure=${m.code}`} className="mrow">
          <span>{m.name}</span>
          <span className="rate"><span className="track"><i style={{ width: `${m.rate*100}%` }} /></span><b>{Math.round(m.rate*100)}%</b></span>
          <span>{m.eligible}</span><span>{m.completed}</span>
          <span className="srcbar">
            <i className="self" style={{ width: `${m.source_split.self_report*100}%` }} />
            <i className="claims" style={{ width: `${m.source_split.claims_confirmed*100}%` }} />
          </span>
        </Link>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: `PriorityWorklist.tsx`** — reuse the existing queue-row component if one exists; otherwise render the worklist rows with a safety/status chip, each linking to `/queue/{care_gap_id}`.

- [ ] **Step 4: `PeriodSelector.tsx`** — a `<select>` of the last ~3 years; `value`/`onChange` lifted to the page.

- [ ] **Step 5: Type-check + commit**

```bash
cd frontend && npx tsc --noEmit
git add frontend/src/pages/overview/
git commit -m "feat(overview): KpiStrip, MeasurePerformanceTable, PriorityWorklist, PeriodSelector"
```

### Task 5: OverviewPage + route + nav + landing

**Files:**
- Create: `frontend/src/pages/overview/OverviewPage.tsx`
- Modify: `frontend/src/App.tsx` (route), `frontend/src/components/AppNav.tsx` (nav item), and the post-login redirect (in `StaffLogin.tsx` / `SessionContext`)

- [ ] **Step 1: `OverviewPage.tsx`** — holds `period` state, TanStack Query `useQuery(["overview", period], () => getOverview(period, token))`, and lays out the approved v5 structure (title + 2×2 KpiStrip upper-left, PriorityWorklist upper-right, MeasurePerformanceTable full-width below). Show a spinner while loading and an error card on failure.

- [ ] **Step 2: Route** — add `<Route path="/overview" element={<OverviewPage />} />` guarded to `payer_admin`/`super_admin` (mirror how existing admin routes gate by `staff.role`).

- [ ] **Step 3: Nav + landing** — add an "Overview" link in `AppNav` for those roles; after login, redirect `payer_admin`/`super_admin` to `/overview` and `care_manager` to `/queue` (adjust the existing post-login `navigate(...)`).

- [ ] **Step 4: Verify in the browser** — run the app, log in as a payer_admin, confirm the dashboard loads with real numbers matching the queue, a measure row navigates to the filtered queue, and the period selector refetches. (Care-manager still lands on the queue.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/overview/OverviewPage.tsx frontend/src/App.tsx frontend/src/components/AppNav.tsx frontend/src/pages/StaffLogin.tsx
git commit -m "feat(overview): OverviewPage, /overview route, nav item, role-based landing"
```

---

## Phase 2 — v1.1 (trend + bonus $)

### Task 6: `MeasureSnapshot` table + migration

**Files:**
- Modify: `backend/app/models.py` (add `MeasureSnapshot`)
- Create: Alembic migration under `backend/migrations/versions/`

- [ ] **Step 1: Add the model**

```python
# backend/app/models.py
class MeasureSnapshot(Base):
    __tablename__ = "measure_snapshots"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    measure_code: Mapped[str] = mapped_column(index=True)
    period: Mapped[int]
    snapshot_date: Mapped[date]
    eligible: Mapped[int]
    completed: Mapped[int]
    rate: Mapped[float]
    __table_args__ = (UniqueConstraint("tenant_id", "measure_code", "period", "snapshot_date",
                                       name="uq_snapshot_day"),)
```

- [ ] **Step 2: Generate + review the migration**

Run: `cd backend && ./.venv/bin/alembic revision --autogenerate -m "add measure_snapshots"`
Then open the generated file and confirm it creates the table + unique index (SQLite: no batch needed for a new table).

- [ ] **Step 3: Apply + test upgrade/downgrade**

Run: `./.venv/bin/alembic upgrade head` then `./.venv/bin/alembic downgrade -1` then `upgrade head` again. Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py backend/migrations/versions/
git commit -m "feat(trend): add measure_snapshots table + migration"
```

### Task 7: Snapshot cron entrypoint

**Files:**
- Create: `backend/app/scripts/run_snapshot_cron.py` (mirror `run_outreach_cron.py`)
- Modify: `infra/modules/ecs` (EventBridge Scheduler + task) — reuse the existing outreach schedule pattern; add a daily rule.
- Test: `backend/tests/test_snapshot.py`

- [ ] **Step 1: Write the failing test** — calling the snapshot function twice for the same day is idempotent and writes one row per active measure with correct eligible/completed.

```python
# backend/tests/test_snapshot.py — asserts one MeasureSnapshot per measure per (tenant, period, day),
# values equal the live aggregation, and a second run does not duplicate rows.
```

- [ ] **Step 2: Run — Expected FAIL.**

- [ ] **Step 3: Implement** a `write_snapshots(db, as_of)` that reuses the Task-1 aggregation (extract the per-measure counting into a shared helper `app/services/overview.py::aggregate_measures(db, tenant_id, period)` and call it from both the endpoint and the cron — DRY), upserting on the unique key.

- [ ] **Step 4: Run — Expected PASS.** Full suite.

- [ ] **Step 5: Commit**

```bash
git add backend/app/scripts/run_snapshot_cron.py backend/app/services/overview.py backend/app/routers/reports.py backend/tests/test_snapshot.py infra/
git commit -m "feat(trend): nightly measure-snapshot cron (reuses overview aggregation)"
```

### Task 8: Wire trend + bonus $ into the endpoint

**Files:**
- Modify: `backend/app/models.py` (`TenantMeasureConfig.dollar_per_gap` nullable column) + migration
- Modify: `backend/app/routers/reports.py` (fill `trend_points` and `bonus_at_risk`)
- Modify: `frontend/src/pages/overview/*` (render the trend arrow; bonus tile already conditional)
- Test: extend `backend/tests/test_overview.py`

- [ ] **Step 1: Add `dollar_per_gap` column + migration** (batch_alter_table for the ALTER — SQLite-safe, per the repo's migration convention).
- [ ] **Step 2: Write failing tests** — `trend_points` = current rate−prior-snapshot rate (in points); `bonus_at_risk` = Σ(remaining × dollar_per_gap), `null` when all configs are null.
- [ ] **Step 3: Implement** — look up the nearest prior-period `MeasureSnapshot`; compute bonus from `TenantMeasureConfig.dollar_per_gap`.
- [ ] **Step 4: Run — Expected PASS.** Full suite. Frontend: render `▲/▼ N pts` when `trend_points != null`.
- [ ] **Step 5: Commit**

```bash
git commit -am "feat(trend): trend deltas + bonus-at-risk in overview endpoint + UI"
```

---

## Self-review checklist (done)
- Spec coverage: KPIs, per-measure rows, self/claims split, worklist, drill-down filter, period selector, role gating/landing, trend (v1.1), bonus $ (v1.1), snapshot cron — all mapped to tasks.
- No placeholders: every code step has real code; the two v1.1 tasks with lighter prose (7 step-1, 8) reference the concrete shared aggregation helper introduced in Task 7.
- Type consistency: `Overview`/`MeasureRow` field names match the endpoint JSON keys (`source_split.self_report/claims_confirmed`, `trend_points`, `bonus_at_risk`) across backend and frontend.
