# Design — Quality Overview Dashboard (Feature A)

**Date:** 2026-07-15
**Product:** cogai-payor / HEDIS Care Gap Platform
**Status:** Approved design, pending implementation plan
**Implement in:** the real source on `JMA-MBP-2026` (GitHub is behind prod — reconcile first). Not from the stale clone.

## 1. Purpose

Give health-plan leadership (payer-admin / super-admin) a single "Quality Overview"
screen that answers, at a glance: how are we doing on each HEDIS measure, who
needs attention now, and what's the financial/quality exposure. It is the
"why-buy-this" surface for a prospective plan (first target: USFHP / St. Vincent's)
and a daily orientation for care managers.

## 2. Goals & non-goals

**Goals**
- One screen: KPI strip + per-measure performance + a safety-first priority worklist.
- Everything reframable by measurement period.
- Reuse existing data (care gaps, screenings, `numerator_source`) — no new external integration.

**Non-goals (this spec)**
- Claims-feed / supplemental-data reconciliation pipeline (separate effort).
- Cross-tenant / platform-wide analytics for super-admin (tenant-scoped only for v1).
- Exports/scheduled reports (fast-follow, noted in §8).

## 3. Layout (approved)

Centered, fixed-max-width card:
- **Header:** title "Quality Overview · <tenant>", period selector (top-right).
- **Upper-left:** 2×2 KPI cluster (number on top, label under): Gap-closure rate,
  Open safety flags (red), Bonus at risk (green), Members reached.
- **Upper-right:** Priority worklist (safety-first), reusing queue rows; "View full queue →".
- **Full-width below:** Performance-by-measure table — Measure · Rate (bar) · Eligible ·
  Completed · Self/Claims split bar. Rows link to that measure's filtered member list.

## 4. Data model

Existing tables cover most of it. Additions:

- **`MeasureSnapshot`** (new) — for trend.
  `id, tenant_id, measure_code, period (year), snapshot_date, eligible, completed, rate, created_at`.
  Unique on `(tenant_id, measure_code, period, snapshot_date)`.
- **`TenantMeasureConfig.dollar_per_gap`** (new nullable column) — per-measure $ used for
  "bonus at risk". Null ⇒ measure excluded from the bonus KPI and the KPI hides if all null.

Derived (no storage):
- eligible = count of `CareGap` for the measure in the period.
- completed = count where `numerator_met = true`.
- rate = completed / eligible.
- self/claims split = counts by `numerator_source` (`self_report` vs `claims_confirmed`).
- remaining = eligible − completed (open opportunity).
- members reached = distinct members with ≥1 gap; enrolled = distinct members in tenant.
- open safety flags = count of `CareGap.safety_flag = true` and not closed.

## 5. API

- **`GET /api/reports/overview?period=<YYYY>`** (role: payer_admin, super_admin; tenant-scoped)
  ```
  {
    "period": 2026,
    "kpis": {
      "gap_closure_rate": 0.58,
      "open_safety_flags": 3,
      "bonus_at_risk": 1200000,        // null if no dollar_per_gap configured
      "members_reached": 1240,
      "members_enrolled": 1560
    },
    "measures": [
      { "code":"mental_health","name":"Depression (DSF)","eligible":820,
        "completed":500,"rate":0.61,"remaining":320,
        "source_split":{"self_report":0.70,"claims_confirmed":0.30},
        "trend_points":4 }                // delta vs prior period snapshot; null pre-v1.1
    ],
    "worklist": [ /* top-N gaps, safety-first, same shape as queue rows */ ]
  }
  ```
- Trend delta pulled from `MeasureSnapshot` (nearest prior-period snapshot). Absent ⇒ `trend_points: null`, UI hides the arrow.

## 6. Trend snapshot job

- A daily task computes per-measure `eligible/completed/rate` per tenant and inserts a
  `MeasureSnapshot` row. **Reuse the existing outreach cron** (EventBridge Scheduler → ECS
  task, `app/scripts/run_outreach_cron.py` pattern) — add a `run_snapshot_cron.py` entrypoint
  or a step in the existing job. Idempotent per `(tenant, measure, period, date)`.

## 7. Frontend

- Route `/overview`; nav item "Overview" for payer_admin/super_admin; **post-login landing**
  for those roles (care managers still land on `/queue`, can open Overview read-only).
- Components: `OverviewPage`, `KpiStrip`, `MeasurePerformanceTable` (row → `/queue?measure=<code>`),
  `PriorityWorklist` (reuse existing queue-row component), `PeriodSelector`.
- Measure filter: `/queue` gains an optional `?measure=` filter (small addition to the queue query).

## 8. Non-functional

- **RBAC:** endpoint restricted to payer_admin/super_admin; tenant-scoped.
- **Performance:** aggregations are simple counts over `care_gaps`; add indexes on
  `(tenant_id, measure_code, status, numerator_met, numerator_source)` if needed.
- **No PHI in aggregates**; worklist reuses the queue's existing de-identified aliases.
- **Fast-follow (not v1):** CSV/PDF export, scheduled leadership email, cohort drill-down.

## 9. Sequencing

1. `GET /api/reports/overview` (aggregations) + frontend (KPIs, table, worklist, period). *Ships without trend.*
2. `MeasureSnapshot` + snapshot cron + trend deltas + bonus-$ config. (v1.1)

## 10. Success criteria

- Overview loads for the USFHP tenant showing correct eligible/completed/rate per measure,
  matching hand-counted queue data.
- Measure row → filtered queue works; period selector reframes all numbers.
- Open-safety-flag KPI matches the queue's safety count.
