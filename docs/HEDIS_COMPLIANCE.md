# HEDIS Compliance & Clinical Sign-off Checklist

This platform implements screening and care-gap logic that **must be reviewed and
signed off by a supervising licensed clinician and a HEDIS/quality compliance lead
before any real member data flows through it.** It is a design specification, not
clinical or regulatory advice, and NCQA's HEDIS specifications are proprietary and
licensed — the summaries below are not a substitute for the current official
measure specification.

## 1. Measure implemented: Depression Screening and Follow-Up (DSF)

| Instrument | License | Source | Placeholder wording? |
|---|---|---|---|
| PHQ-9 | Public | Pfizer (free) | No |
| GAD-7 | Public | Pfizer (free) | No |

- [ ] Obtain the current NCQA HEDIS DSF measure specification (technical spec, not
      this summary) and confirm eligible population, exclusions, and reporting
      periods against `backend/app/measures/mental_health.py`
- [ ] Confirm PHQ-9/GAD-7 wording matches the current official version
- [ ] Obtain validated non-English translations for the member's preferred language
      before enabling a locale (`Member.preferred_language`) in production
- [ ] Confirm whether your plan's DSF reporting requires a *specific* standardized
      depression screening tool roster, or accepts PHQ-9 generally

### Thresholds, eligibility & follow-up window (review each)

Everything below is a defensible starting heuristic implemented in
`backend/app/measures/mental_health.py` and `backend/app/scoring.py` — **not an
empirically validated or NCQA-audited model.**

- [ ] Eligibility: age >= 12 (`is_eligible`) — confirm against the actual DSF
      eligible population and any plan-specific exclusions (e.g. hospice, prior
      diagnosis exclusions)
- [ ] PHQ-9 severity cutoffs — 5 / 10 / 15 / 20 = mild / moderate / moderately
      severe / severe; item 9 > 0 = safety flag
- [ ] GAD-7 severity cutoffs — 5 / 10 / 15 = mild / moderate / severe
- [ ] Follow-up window — currently 30 days for moderate-or-higher PHQ-9, 1 day for
      a positive safety item (`follow_up_window_days`). Confirm against your
      plan's actual follow-up documentation requirement for numerator credit.
- [ ] Numerator definition — currently "screening completed" satisfies the
      numerator regardless of score; confirm this matches the measure's actual
      numerator logic (some HEDIS measures require the follow-up step itself for
      full credit, not just the screening)

### Safety & escalation

- [ ] Define the **real-time escalation pathway** for PHQ-9 item-9 positives
      (named responsible clinician(s)/care manager on-call routing, response SLA)
      — currently the platform only opens a 1-day follow-up window and surfaces a
      safety badge in the care manager queue; it does not page anyone.
- [ ] Confirm crisis resources shown to members (988, Crisis Text Line) are
      correct and current for the member's state/region
- [ ] Confirm consent language (`backend/app/notifications/templates.py`,
      SMS opt-out footer) against TCPA and your state's requirements

## 2. Measure implemented: Breast Cancer Screening (BCS)

Implemented in `backend/app/measures/breast_cancer.py`. Structurally different
from DSF: no licensed instrument, no self-administered questionnaire — it's a
completion-confirmation + scheduling-assistance flow.

- [ ] Obtain the current NCQA HEDIS BCS measure specification and confirm
      eligible population, exclusions, and measurement period (commonly a
      27-month lookback, not a calendar year — `CareGap.period` here is
      currently just the calendar year, which **does not** match BCS's actual
      lookback window; fix before relying on this for a real submission)
- [ ] Eligibility as implemented: female members aged 50-74 (`is_eligible`) —
      confirm against the actual measure's age band and any exclusions
      (e.g. bilateral mastectomy)
- [ ] **Numerator source** — this module currently accepts **member self-report**
      ("I've had a mammogram") as numerator-met. Real HEDIS BCS numerator credit
      is normally driven by **claims/encounter data**, not self-report. Decide
      whether self-report is acceptable as an interim/soft signal only, or
      whether numerator credit must be gated on a claims feed reconciliation
      step before this measure's rate is reported anywhere official.
- [ ] `Member.sex` is currently a simple F/M/U field populated at roster
      ingestion — confirm the payer's eligibility feed is the right source of
      truth for this, not member self-report, for measure eligibility purposes
- [ ] Scheduling-help follow-up window (14 days) — confirm against your care
      management team's actual SLA for reaching out to help schedule

## 3. Measure implemented: Colorectal Cancer Screening (COL)

Implemented in `backend/app/measures/colorectal_cancer.py`. Same self-report +
scheduling-assistance shape as BCS — no licensed instrument.

- [ ] Obtain the current NCQA HEDIS COL measure specification. Real COL has
      **multiple modalities with different recency windows** (FIT/FOBT within
      1 year, flexible sigmoidoscopy within 5 years, CT colonography within 5
      years, colonoscopy within 10 years) — this module collects an optional
      `screening_type` on submission but does **not** yet apply modality-specific
      recency logic; it currently treats any "yes" as numerator-met regardless
      of which test or when. Fix before relying on this for a real submission.
- [ ] Eligibility as implemented: ages 45-75, no sex restriction — confirm
      against the current measure spec (age band was recently lowered from 50
      to 45 industry-wide; confirm which version your plan reports against)
      and any exclusions (e.g. total colectomy, hospice)
- [ ] **Numerator source** — self-report, same caveat as BCS: real HEDIS COL
      credit is normally claims/encounter-based. Decide whether self-report is
      an interim signal only.
- [ ] `CareGap.period` is a calendar year — same mismatch as BCS, worse here
      given COL's multiple different lookback windows per modality.

## 4. Measure implemented: Controlling High Blood Pressure (CBP)

Implemented in `backend/app/measures/blood_pressure.py`. First measure whose
eligibility depends on clinical history (`Member.conditions` must include
`"hypertension"`), not just age/sex — and the first non-mental-health measure
with its own safety-flag concept (hypertensive crisis).

- [ ] Obtain the current NCQA HEDIS CBP measure specification and confirm
      eligible population (implemented: ages 18-85 with a hypertension
      diagnosis) and exclusions (e.g. ESRD, pregnancy, frailty)
- [ ] **`Member.conditions` is populated at roster ingestion from the payer's
      feed** (or manually via the API) — confirm this is a reliable source for
      diagnosis data, not something inferred from member self-report. A member
      incorrectly missing `"hypertension"` on their record will never be asked
      about their blood pressure at all.
- [ ] **Numerator source** — this module accepts a **self-reported home BP
      reading** as the numerator signal (systolic < 140 and diastolic < 90 =
      controlled). Real HEDIS CBP numerator credit needs the **most recent
      outpatient BP reading in the medical record**, not a home/self-reported
      value. This is meaningfully different from the BCS/COL self-report
      caveat — a home cuff reading and a clinical reading can differ, and using
      this for anything beyond member engagement/outreach triage needs
      explicit clinical sign-off.
- [ ] Crisis threshold (systolic >= 180 or diastolic >= 120) — this is a widely
      used hypertensive-crisis threshold, but confirm the exact wording/values
      and the member-facing message (`ScreeningFlow.tsx`'s `BloodPressureFlow`)
      with your clinical team before this reaches a real member. As shipped it
      tells the member to call 911 or go to the ER — verify that's the guidance
      your plan wants given a home reading (vs. e.g. "call your doctor's office
      now" for a lower-acuity threshold).
- [ ] Follow-up windows: 1 day for crisis-range, 14 days for above-goal but not
      crisis — confirm against your care management team's actual SLA

## 5. Measure implemented: Comprehensive Diabetes Care — HbA1c Testing & Control

Implemented in `backend/app/measures/diabetes.py`. Condition-gated like CBP
(`Member.conditions` must include `"diabetes"`).

- [ ] **This covers only the HbA1c testing/control sub-measure.** The full
      HEDIS Comprehensive Diabetes Care (CDC) measure bundle includes several
      other sub-measures not implemented here — eye exam (retinal screening)
      and nephropathy (kidney disease) monitoring being the two most
      significant omissions. Don't report this module's rate as "CDC" without
      qualifying which sub-measure it is.
- [ ] Obtain the current NCQA HEDIS CDC (HbA1c) specification and confirm
      eligible population (implemented: ages 18-75 with a diabetes diagnosis)
      and exclusions
- [ ] **Numerator source** — self-reported "I had the test" plus an optional
      self-reported value. Real HEDIS credit needs a lab-confirmed result, not
      self-report, and the "poor control" threshold used here (>9.0%) is a
      reasonable outreach-triage heuristic but is **not** the HEDIS "poor
      control" numerator definition for the actual measure (which HEDIS
      inverts — CDC's headline sub-measure is typically framed as "% with
      *poor* control >9.0", i.e. a measure you want a *low* rate on; confirm
      you're not accidentally reporting this inverted against the wrong
      polarity when this feeds anywhere official).
- [ ] Follow-up window (30 days) for both "not tested" and "poor control" —
      confirm against your care team's actual outreach SLA, and consider
      whether poor control should have a shorter window than "not yet tested"

## 6. Measure implemented: Childhood Immunization Status (CIS)

Implemented in `backend/app/measures/childhood_immunization.py`. First
**dependent-scoped** measure (`subject_type = "dependent"`) — eligibility and
the submitted response are about the guardian's child (a `Dependent` row), not
the account holder (`Member`) who receives outreach and authenticates. See
`app/models.py::Dependent` and `app/routers/dependents.py`.

- [ ] Obtain the current NCQA HEDIS CIS measure specification. Real CIS
      eligibility is children turning 2 **during the measurement year**
      (this module simplifies to "is exactly 2 years old as of today," which
      drifts out of sync with a proper measurement-year window — same
      `CareGap.period`-as-calendar-year issue as BCS/COL, see below).
- [ ] **Numerator source** — real HEDIS CIS numerator credit requires specific
      combinations of vaccine doses ("Combo 10" and similar), verified against
      immunization registry or claims data. This module is a **self-report
      proxy only** ("are immunizations up to date?") — it cannot produce a
      real CIS rate on its own. Treat it as an engagement/outreach signal, not
      a measure calculation, until real immunization data is integrated.
- [ ] Guardian consent: confirm your consent/privacy language covers a
      guardian receiving outreach *about* their dependent, not just about
      themselves — this is a different consent scope than every other measure
      in this platform.

## 7. Measure implemented: Well-Child Visits (WCV)

Implemented in `backend/app/measures/well_child_visits.py`. Dependent-scoped,
same shape as CIS.

- [ ] Obtain the current NCQA HEDIS WCV measure specification. Real WCV covers
      ages 0-21 with **different visit-count requirements by age band**
      (e.g. 6+ visits by 15 months for infants) — this module simplifies to a
      single "at least one well-child visit in the last 12 months" self-report
      for ages 3-17 only. Infants/toddlers (0-2) and young adults (18-21) are
      not covered at all; don't assume this module's denominator matches the
      real WCV eligible population.
- [ ] **Numerator source** — self-report, same caveat as BCS/COL/CIS: real
      HEDIS credit is claims/encounter-based.

## 8. Sign-off

| Role | Name | Signature | Date |
|---|---|---|---|
| Supervising licensed clinician | | | |
| HEDIS / quality compliance lead | | | |
| Institutional / legal review | | | |

> Nothing in this product constitutes clinical, regulatory, or legal advice.
> Validate all instruments, thresholds, eligibility rules, and escalation
> protocols with a licensed clinical supervisor, your HEDIS auditor, and legal
> counsel before any real member outreach.

## 9. Reporting & submission

- [ ] Confirm `GET /api/reports/hedis` numerator/denominator logic against your
      HEDIS auditor's expectations before using it for any real submission
      (currently: denominator = every care-gap row for the period not excluded;
      numerator = per-measure `numerator_met`, see each measure's module)
- [ ] Determine whether this platform's data needs to feed a HEDIS supplemental
      data submission to the payer's primary quality reporting system, or is the
      system of record itself
- [ ] Exclusion workflow exists (`GapStatus.excluded`, requires a reason) — confirm
      the reasons your care managers use actually match acceptable HEDIS
      exclusion categories, since right now it accepts any free-text reason
- [ ] Fix `CareGap.period` to be measure-appropriate — calendar year works for
      DSF/CBP/CDC (annual measures) but **not** for BCS/COL/CIS/WCV, which use
      multi-year or non-calendar measurement windows

## 10. Adding a new measure module

To add a measure beyond the seven implemented so far:

1. Implement `Measure` (`backend/app/measures/base.py`): `is_eligible`,
   `evaluate_submission`, `follow_up_window_days`.
2. Register it in `backend/app/measures/__init__.py`.
3. Add a section to this document with its own instrument-licensing/eligibility/
   numerator-source table before enabling it for any real tenant.
4. Decide the numerator source up front — self-report (BCS/COL), a structured
   instrument (DSF), a self-reported clinical value (CBP/CDC), or claims/
   encounter data — and be explicit in this doc about which one and why, since
   that decision drives whether the measure's HEDIS rate can be reported as-is
   or needs claims reconciliation first.
5. If eligibility depends on diagnosis/condition rather than just age/sex, use
   `Member.conditions` (see CBP/CDC) rather than inventing a new field —
   confirm the roster feed populating it is a real diagnosis source, not
   inferred from anything the member self-reports.
6. **If the measure's subject is a dependent, not the account holder** (any
   further pediatric measure), set `subject_type = "dependent"` on the module
   and use the `Dependent` model (`app/models.py`, `app/routers/dependents.py`)
   — built for CIS/WCV. A dependent's `CareGap` keeps `member_id` pointing at
   the guardian (who receives outreach and authenticates) and `dependent_id`
   pointing at who the measure is actually about; `is_eligible` is evaluated
   against the `Dependent`, and `_open_care_gaps_for_dependent`
   (`app/routers/members.py`) opens the gap, not `_open_care_gaps_for_member`.
   Don't bolt a dependent's data onto an adult `Member` row.
