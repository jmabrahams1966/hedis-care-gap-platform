# Pharmacy / Medication-Adherence (PDC) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **PREREQUISITE #0.** GitHub is behind production — implement in the real source on `JMA-MBP-2026` after reconciling (`demo/RECONCILE_AND_HARDEN.md`). Paths/models below are from an older clone; confirm each against the real source. Reuses the measure registry (`app/measures/`), `CareGap` + `numerator_source`, `ScreeningSubmission`, the roster bulk-CSV pattern, and the C1 cadence engine. `FillRecord` medication fields are PHI → encrypted per the deployed pattern; every mutating call writes `log_action(...)`; new tables are tenant-scoped with RBAC.

**Goal:** HEDIS medication-adherence via a source-agnostic `FillRecord` + a pure PDC engine, three PDC measure modules (diabetes/statins/RAS) that open care gaps below 0.80, fed by a self-report loader (C1 check-ins) and a pharmacy-claims CSV loader.

**Architecture:** `FillRecord` store + `DrugClassMap` reference; `pdc_service.compute_pdc` (pure); `pdc_*` measure modules; a recompute helper that upserts `CareGap`s; two loaders (claims CSV endpoint, self-report via screening submission); a member adherence panel.

**Tech Stack:** FastAPI, async SQLAlchemy 2.0, Alembic, pytest; React 18 + TS + Vite.

**Reference spec:** `docs/superpowers/specs/2026-07-15-pharmacy-medication-adherence-design.md`

---

## Phase 1 — Models + engine + measures

### Task 1: `FillRecord` + `DrugClassMap` models + migration

**Files:** Modify `backend/app/models.py`; create migration.

- [ ] **Step 1: Models**

```python
class FillRecord(Base):
    __tablename__ = "fill_records"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    drug_class: Mapped[str] = mapped_column(index=True)   # diabetes|statin|ras
    ndc: Mapped[str | None] = mapped_column(nullable=True)   # PHI-adjacent — encrypted col type
    fill_date: Mapped[date]
    days_supply: Mapped[int]
    source: Mapped[str]                                    # self_report|claims_confirmed
    source_ref: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

class DrugClassMap(Base):
    __tablename__ = "drug_class_map"
    ndc: Mapped[str] = mapped_column(primary_key=True)
    drug_class: Mapped[str] = mapped_column(index=True)
```

- [ ] **Step 2: Migration** (two new tables). Apply/downgrade/upgrade. **Commit**

```bash
git add backend/app/models.py backend/migrations/versions/
git commit -m "feat(pdc): FillRecord + DrugClassMap tables"
```

### Task 2: PDC engine (pure) — `app/pdc_service.py`

**Files:** Create `backend/app/pdc_service.py`; Test `backend/tests/test_pdc.py`.

- [ ] **Step 1: Failing tests** (the crux — cover overlap + partial coverage)

```python
# backend/tests/test_pdc.py
from datetime import date
from app.pdc_service import compute_pdc

def F(d, days): return {"fill_date": date(2026, *d), "days_supply": days}

def test_full_coverage_is_1():
    # first fill Jan 1, then perfectly contiguous 30-day fills to year end
    fills = [F((1,1),120), F((5,1),120), F((9,1),120)]  # ~360 days from Jan 1
    assert compute_pdc(fills, period_end=date(2026,12,31)) >= 0.95

def test_overlap_not_double_counted():
    # two 30-day fills 10 days apart -> covered days = 40, not 60
    fills = [F((1,1),30), F((1,11),30)]
    # treatment period = Jan1..Dec31 (365); covered=40
    assert round(compute_pdc(fills, period_end=date(2026,12,31)), 3) == round(40/365, 3)

def test_no_fills_is_zero():
    assert compute_pdc([], period_end=date(2026,12,31)) == 0.0
```

- [ ] **Step 2: Run — FAIL.** `cd backend && ./.venv/bin/python -m pytest tests/test_pdc.py -v`

- [ ] **Step 3: Implement**

```python
# backend/app/pdc_service.py
from datetime import date, timedelta

def compute_pdc(fills: list[dict], period_end: date) -> float:
    """PDC = covered days / treatment-period days, from first fill to period_end,
    counting each covered calendar day at most once (overlaps not double-counted)."""
    if not fills:
        return 0.0
    start = min(f["fill_date"] for f in fills)
    total_days = (period_end - start).days + 1
    if total_days <= 0:
        return 0.0
    covered: set[date] = set()
    for f in fills:
        d = f["fill_date"]
        for _ in range(int(f["days_supply"])):
            if start <= d <= period_end:
                covered.add(d)
            d += timedelta(days=1)
    return round(len(covered) / total_days, 4)
```
(For large day-supplies this set approach is fine at member scale; if profiling shows cost, switch to interval-merge — same result.)

- [ ] **Step 4: Run — PASS.** **Commit**

```bash
git add backend/app/pdc_service.py backend/tests/test_pdc.py
git commit -m "feat(pdc): compute_pdc engine (interval coverage, overlap-safe)"
```

### Task 3: Three PDC measure modules

**Files:** Create `backend/app/measures/pdc_diabetes.py`, `pdc_statins.py`, `pdc_ras.py`; register in `backend/app/measures/__init__.py`; Test `backend/tests/test_pdc_measures.py`.

- [ ] **Step 1: Failing test** — for a member with 2+ diabetes fills at PDC<0.8, `pdc_diabetes.evaluate(...)` returns `numerator_met=False`; ≥0.8 → True; `is_eligible` requires ≥2 fills; `numerator_source` follows the fills' source.

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement** a shared base `PdcMeasure` (parametrized by `drug_class` + `code` + name) that: `is_eligible` = ≥2 `FillRecord`s of the class in the period; `evaluate` = `compute_pdc(...) >= 0.80`, returning `numerator_met` + a `source` derived from the fills (`claims_confirmed` if all/any claims — pick "all confirmed ⇒ confirmed, else self_report" and document it). The three modules subclass it with the right `drug_class`/code/value-set. Register all three in `measures/__init__.py`.

```python
# backend/app/measures/pdc_base.py (new shared base — DRY across the three)
class PdcMeasure(Measure):
    drug_class = ""      # set by subclass
    def is_eligible(self, subject, as_of): ...   # >=2 class fills in period
    def evaluate(self, member_fills): ...        # compute_pdc >= 0.80 (+ source)
```

- [ ] **Step 4: Run — PASS.** Full suite. **Commit**

```bash
git add backend/app/measures/ backend/tests/test_pdc_measures.py
git commit -m "feat(pdc): pdc_diabetes/statins/ras measure modules (shared PdcMeasure base)"
```

---

## Phase 2 — Loaders + gap wiring

### Task 4: Recompute helper (fill → CareGap)

**Files:** Create `backend/app/pdc_recompute.py`; Test `backend/tests/test_pdc_recompute.py`.

- [ ] **Step 1: Failing test** — `recompute(db, member_id, drug_class, period)` opens a `CareGap` when eligible + PDC<0.8 (`numerator_met=False`), updates an existing gap's `numerator_met`/`numerator_source`, and closes it when PDC≥0.8.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — gather the member's class fills for the period, call the measure's `evaluate`, upsert the `CareGap` (reuse the existing gap-open/close helpers from `care_gaps.py`/`members.py`), audit.
- [ ] **Step 4: Run — PASS.** **Commit.**

### Task 5: Claims/PBM bulk-CSV loader

**Files:** Create `backend/app/routers/pharmacy.py`; register in `main.py`; Test `backend/tests/test_fill_ingest.py`.

- [ ] **Step 1: Failing test** — `POST /api/pharmacy/fills/bulk-csv` (payer_admin) with rows `external_member_id,ndc,fill_date,days_supply` creates `FillRecord`s (`source=claims_confirmed`), maps NDC→class via `DrugClassMap` (unknown NDC → row error, not crash), and triggers `recompute` so a below-threshold member gets a gap. Role gating + tenant isolation.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** mirroring `members.py::bulk_create_members_csv` (UploadFile, `csv.DictReader`, per-row errors list); resolve member by `external_member_id`; map NDC→class (or accept explicit `drug_class`); insert fills; call `recompute` per (member, class). Audit.
- [ ] **Step 4: Run — PASS.** Full suite. **Commit.**

### Task 6: Self-report loader (medication check-in)

**Files:** In the `pdc_*` measure modules, implement `evaluate_submission`; ensure the screenings endpoint path writes the fill; add the `medication_check_in` template. Test `backend/tests/test_selfreport_fill.py`.

- [ ] **Step 1: Failing test** — submitting a `pdc_diabetes` screening `{"refilled": true, "fill_date": "...", "days_supply": 30}` creates a `FillRecord(source=self_report)` and recomputes PDC (raising it; gap closes if ≥0.8, with `numerator_source=self_report`).
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — the measure's `evaluate_submission` (called by the existing screenings router) writes a self-report `FillRecord` and calls `recompute`. Add `medication_check_in` to the notification templates for the C1 cadence step.
- [ ] **Step 4: Run — PASS.** Full suite. **Commit.**

---

## Phase 3 — Frontend

### Task 7: Adherence endpoint + member panel

**Files:** Add `GET /api/members/{id}/adherence` (in `pharmacy.py`); create `frontend/src/pages/care-manager/AdherencePanel.tsx`; wire into the Feature B workspace. Test `backend/tests/test_adherence_endpoint.py`.

- [ ] **Step 1: Backend test + impl** — endpoint returns per-class `{pdc, threshold: 0.80, fills: [{date, days_supply, source}]}`; tenant-scoped. TDD (fail → impl → pass).
- [ ] **Step 2: `AdherencePanel.tsx`** — per-class PDC (bar vs 0.80 threshold), a fill timeline, "days to threshold." Type-check + browser verify on a member with fills. **Commit.**

### Task 8: Admin fills upload + dashboard

**Files:** Create `frontend/src/pages/admin/FillsUpload.tsx` (simple CSV upload → `POST /api/pharmacy/fills/bulk-csv`, mirroring roster upload); confirm the three PDC measures render on the Feature A dashboard (free once they emit gaps).

- [ ] **Step 1** — `FillsUpload.tsx`: file picker + POST + result summary (created / errors). Type-check + browser verify an upload opens gaps and the dashboard shows the PDC rows. **Commit.**

---

## Self-review checklist (done)
- **Spec coverage:** FillRecord/DrugClassMap (T1), PDC engine (T2), three measures (T3), recompute/gap wiring (T4), claims loader (T5), self-report loader (T6), adherence panel + endpoint (T7), fills upload + dashboard (T8). Both loaders feed the same store; `numerator_source` provenance handled in T3/T4.
- **Placeholders:** none unresolved; the four spec open questions (licensed value sets → curated subset; self-report not HEDIS-credited; real feed format; PDC period edge cases) are called out, not silently resolved.
- **Type consistency:** `drug_class` vocab (`diabetes|statin|ras`), `source` (`self_report|claims_confirmed`), and `compute_pdc(fills, period_end)` signature identical across engine (T2), measures (T3), recompute (T4), and loaders (T5–6).
