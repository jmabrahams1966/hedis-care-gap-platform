# Design — Pharmacy / Medication-Adherence (PDC) (Feature C2)

**Date:** 2026-07-15
**Product:** cogai-payor / HEDIS Care Gap Platform
**Status:** Approved design, pending implementation plan
**Implement in:** the real source on `JMA-MBP-2026` (GitHub is behind prod — reconcile first).

## 1. Purpose

Add HEDIS medication-adherence (PDC) to the platform: track pharmacy fills, compute
Proportion of Days Covered per drug class, generate care gaps when PDC < 0.80, and drive
adherence outreach through the C1 cadence engine. Designed **source-agnostic** so it ships
on self-report now and slots in a real pharmacy-claims/PBM feed (TRICARE = Express Scripts)
later without redesign.

## 2. Goals & non-goals

**Goals**
- Normalized `FillRecord` + a pure PDC engine, decoupled from data source.
- Two loaders → same store: self-report (via C1 cadence / screening) and pharmacy-claims CSV.
- Three PDC measure modules — **Diabetes, Statins, RAS antagonists** — as first-class HEDIS
  measures (care gaps, dashboard, outreach), reusing the measure registry + `numerator_source`.

**Non-goals (this spec)**
- SUPD/SPC statin-use measures (different shape — dispensing event, not PDC) — later.
- A live Express Scripts/Surescripts integration — v1 ingests a normalized CSV; the real
  feed gets a thin adapter when contracted.
- Licensed NCQA value sets — v1 uses a curated subset (see Open Questions).

## 3. Architecture

Source-agnostic core, pluggable loaders, fits the existing measure-module pattern:
```
 self-report check-in (C1) ┐
                           ├─→ FillRecord store ──→ pdc_service ──→ PDC measure modules ──→ CareGap
 pharmacy-claims CSV ──────┘        (+ DrugClassMap)                (diabetes/statins/ras)   (queue/dashboard/outreach)
```

## 4. Data model

- **`FillRecord`** — `id, tenant_id, member_id, drug_class (diabetes|statin|ras), ndc (nullable),
  fill_date (date), days_supply (int), source (self_report|claims_confirmed), source_ref (nullable),
  created_at`. Medication fields are PHI → encrypted per the deployed pattern.
- **`DrugClassMap`** — `ndc (pk), drug_class`. Reference table, seeded from a curated subset of the
  NCQA medication lists for the three classes.
- **Three measure modules** in `app/measures/`: `pdc_diabetes.py`, `pdc_statins.py`, `pdc_ras.py`,
  registered in `measures/__init__.py`. Reuse `CareGap` + `numerator_source` (no new gap tables).

## 5. PDC engine (`app/pdc_service.py`)

Pure function `compute_pdc(fills, drug_class, period) -> float`:
- **Treatment period:** first in-period fill date → period end (measurement year end).
- **Days covered:** union of `[fill_date, fill_date + days_supply)` intervals across the class's
  fills, clipped to the treatment period, counting each calendar day at most once (overlaps from
  early refills do not double-count).
- **PDC** = covered_days / treatment_period_days (0.0 if no treatment period).
Deterministic, no I/O — unit-testable in isolation.

## 6. Measure modules (each implements the existing `Measure` interface)

- **Eligible (denominator):** ≥ 2 dispensing events (`FillRecord`s) of the class in the period —
  the standard PDC denominator.
- **Numerator met:** `compute_pdc(...) >= 0.80`.
- **`numerator_source`:** `claims_confirmed` if the fills feeding the PDC are `claims_confirmed`,
  else `self_report`. So **self-report PDC is visibly not claims-grade** (surfaces in Feature A's
  self/claims bar) and does not officially credit HEDIS.
- **Follow-up:** below threshold ⇒ open/keep the gap; drives the C1 "medication adherence" sequence.

## 7. Loaders

- **Self-report:** a "medication check-in" is a `ScreeningSubmission` for a `pdc_*` measure. Its
  `evaluate_submission({"refilled": true, "fill_date": ..., "days_supply": ...})` writes a
  `FillRecord(source=self_report)` and triggers recompute. Delivered via a C1 cadence step
  (`template_key = "medication_check_in"`).
- **Claims/PBM:** `POST /api/pharmacy/fills/bulk-csv` (payer_admin) — columns
  `external_member_id, ndc, fill_date, days_supply` (or explicit `drug_class`). Maps NDC→class via
  `DrugClassMap`; writes `FillRecord(source=claims_confirmed)`; recomputes affected members.
  Mirrors the roster bulk-CSV ingestion pattern.

## 8. Recompute flow

On any new `FillRecord` (either source): recompute the member's PDC for that class in the current
period → upsert/refresh the `CareGap` (`numerator_met`, `numerator_source`) → if ≥ 0.80 close the
gap; if < 0.80 keep it open (C1 continues the adherence cadence). Eligible members with no gap yet
(≥2 fills, PDC < 0.80) get one opened. All writes audited.

## 9. API

- `POST /api/pharmacy/fills/bulk-csv` (payer_admin) — claims loader.
- `GET /api/members/{id}/adherence` (care_manager+) — per-class PDC, threshold, fill timeline.
- Self-report enters through the existing screenings endpoint (a `pdc_*` measure submission).

## 10. Frontend

- **Care-manager (Feature B workspace):** med-adherence panel — PDC per class, fill timeline,
  "days to threshold."
- **Admin:** pharmacy fills upload (claims loader) — API-first, a simple upload UI mirroring roster.
- **Member:** medication check-in flow (screening variant) via C1.
- **Dashboard (A):** the three PDC measures appear in the per-measure table for free.

## 11. Open questions

1. **NCQA medication value sets are licensed content** — v1 uses a curated representative subset per
   class; official reporting needs the licensed lists + compliance sign-off (`docs/HEDIS_COMPLIANCE.md`).
2. **Self-report PDC is engagement-grade, not HEDIS-credited** — labeled `self_report`; confirm framing.
3. **Real claims feed format** (Express Scripts/DoD) unknown → normalized CSV now; adapter when contracted.
4. **PDC period edge cases** (member enrolled mid-year, drug switches within class) — v1 uses
   first-in-period fill → period end; refine with clinical/HEDIS review.

## 12. Sequencing

1. `FillRecord` + `DrugClassMap` models + migration.
2. `pdc_service` engine (+ curated DrugClassMap seed).
3. Three `pdc_*` measure modules + registry.
4. Claims bulk-CSV loader; self-report loader (screening path) + recompute/gap wiring.
5. Frontend: adherence panel; fills upload; (dashboard is free).

## 13. Success criteria

- Upload a claims CSV with 2+ diabetic fills covering < 80% of days ⇒ a `pdc_diabetes` gap opens with
  `numerator_source=claims_confirmed`, PDC value correct against a hand calculation.
- A self-report refill check-in raises PDC and, if ≥ 0.80, closes the gap (`source=self_report`).
- The three PDC measures show on the Feature A dashboard with the correct self/claims split.
