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

## 3. Sign-off

| Role | Name | Signature | Date |
|---|---|---|---|
| Supervising licensed clinician | | | |
| HEDIS / quality compliance lead | | | |
| Institutional / legal review | | | |

> Nothing in this product constitutes clinical, regulatory, or legal advice.
> Validate all instruments, thresholds, eligibility rules, and escalation
> protocols with a licensed clinical supervisor, your HEDIS auditor, and legal
> counsel before any real member outreach.

## 4. Reporting & submission

- [ ] Confirm `GET /api/reports/hedis` numerator/denominator logic against your
      HEDIS auditor's expectations before using it for any real submission
      (currently: denominator = every care-gap row for the period not excluded;
      numerator = per-measure `numerator_met`, see each measure's module)
- [ ] Determine whether this platform's data needs to feed a HEDIS supplemental
      data submission to the payer's primary quality reporting system, or is the
      system of record itself
- [ ] Build the exclusion workflow (`GapStatus.excluded`) — currently a status
      value exists but nothing in the UI sets it yet
- [ ] Fix `CareGap.period` to be measure-appropriate (calendar year works for
      DSF; BCS needs a rolling/lookback period, not a fixed year)

## 5. Adding a new measure module

To add a measure beyond mental health and breast cancer screening:

1. Implement `Measure` (`backend/app/measures/base.py`): `is_eligible`,
   `evaluate_submission`, `follow_up_window_days`.
2. Register it in `backend/app/measures/__init__.py`.
3. Add a section to this document with its own instrument-licensing/eligibility/
   numerator-source table before enabling it for any real tenant.
4. Decide the numerator source up front — self-report (like BCS here), a
   structured instrument (like DSF here), or claims/encounter data — and be
   explicit in this doc about which one and why, since that decision drives
   whether the measure's HEDIS rate can be reported as-is or needs claims
   reconciliation first.
