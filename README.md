# HEDIS Care Gap Platform

Multi-tenant remote patient outreach and screening for health plans — SMS/email
check-ins that close HEDIS care gaps. Health plans elect which measure modules
are active for their members; five are implemented so far (Depression
Screening & Follow-Up, Breast Cancer Screening, Colorectal Cancer Screening,
Controlling High Blood Pressure, Diabetes HbA1c Testing & Control), each
plugging into the same tenant/member/outreach engine without touching its
schema.

> **Status: early scaffold.** Backend and frontend run end-to-end locally with
> synthetic demo data. AWS infrastructure is written as Terraform but **not
> applied** — see `infra/README.md`. Nothing here has had clinical or legal
> sign-off — see `docs/HEDIS_COMPLIANCE.md`.

## Architecture

```
                    +--------------------+
                    |  CloudFront + S3   |
                    |  React frontend    |
                    |  app.<domain>      |
                    +----------+---------+
                               |
                               | HTTPS
                               v
                    +--------------------+
                    |  ALB -> ECS Fargate |
                    |  FastAPI backend    |
                    |  api.<domain>       |
                    +----------+---------+
                               |
              +----------------+----------------+
              |                |                 |
    +---------v---+   +--------v-------+  +------v-------+
    | Aurora       |   | AWS SES        |  | AWS End User |
    | Postgres     |   | Email outreach |  | Messaging    |
    | (private)    |   |                |  | SMS outreach |
    +--------------+   +----------------+  +--------------+
```

**Stack:** React 18 + TypeScript + Vite (frontend) · FastAPI + async SQLAlchemy
(backend) · Aurora Serverless v2 Postgres · AWS SES + End User Messaging for
outreach · ECS Fargate + Route 53 + CloudFront for hosting.

## Repository structure

```
backend/
  app/
    models.py            Tenant, Member (incl. conditions for diagnosis-gated measures),
                          Measure, TenantMeasureConfig, CareGap, OutreachAttempt,
                          ScreeningSubmission, CaseNote, AuditLog
    scoring.py            Server-side PHQ-9 / GAD-7 scoring (client never scores)
    measures/             Pluggable measure module registry
      base.py             Measure interface every module implements
      mental_health.py     DSF: PHQ-9 + GAD-7, age-gated
      breast_cancer.py     BCS: self-report + scheduling-assist, age+sex-gated
      colorectal_cancer.py COL: self-report + scheduling-assist, age-gated
      blood_pressure.py    CBP: self-reported reading, condition-gated, crisis safety flag
      diabetes.py          CDC (HbA1c subset): self-reported test/value, condition-gated
    notifications/        SES email + SMS senders, templates (dev-mode safe)
    routers/               auth, tenants, members, screenings, care_gaps, outreach, reports
    seed.py                Demo tenant + 7 synthetic members (dev_mode only)
frontend/
  src/
    pages/member/          Magic-link entry, verify, PHQ-9/GAD-7 flow, safety card
    pages/care-manager/     De-identified triage queue, case detail, notes
    pages/admin/            Per-tenant measure module toggles
    pages/superadmin/       Tenant (health plan) provisioning
infra/                     Terraform: VPC, Aurora, ECS Fargate, CloudFront, Route 53
docs/
  HEDIS_COMPLIANCE.md       Instrument licensing, thresholds, sign-off checklist
  SECURITY_HIPAA.md         Encryption, audit logging, access control, BAA checklist
  DEPLOYMENT.md             How to actually stand this up on AWS
```

## Run locally

**Backend**
```bash
cd backend
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m uvicorn app.main:app --reload --port 8099
```
No `.env` needed for dev — SQLite + `dev_mode=true`, seeds a `demo` tenant with 7
synthetic members and 3 staff accounts (see `backend/app/seed.py` for credentials)
on first boot. In dev mode, magic-link tokens are returned in the API response
instead of being texted/emailed, and outreach sends are logged, not dispatched.

**Tests**
```bash
cd backend
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest tests/ -v
```
Unit tests for scoring (`tests/test_scoring.py`) and all five measure modules
(`tests/test_measures.py`) need no DB. `tests/test_api_flow.py` drives the FastAPI
app end-to-end over `httpx.ASGITransport` against a throwaway SQLite file —
tenant/member creation, magic-link auth, multiple measure flows, condition-gated
eligibility, exclusions, and the HEDIS report.

**Frontend**
```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, expects the backend on :8099
```

## How a measure module works

A "measure" (`backend/app/measures/base.py`) is eligibility rules + submission
evaluation + a follow-up window. Three distinct shapes exist so far:

- **Structured instrument** (`mental_health.py` — DSF): members 12+ are
  eligible, completing PHQ-9 (+GAD-7) satisfies the numerator, and a
  moderate-or-higher score or a positive safety item opens a follow-up.
- **Self-report + scheduling-assist** (`breast_cancer.py`, `colorectal_cancer.py`
  — BCS/COL): no instrument, just "have you completed this?" and an offer to
  help schedule if not. Age (+ sex, for BCS) gated.
- **Self-reported clinical reading, condition-gated** (`blood_pressure.py`,
  `diabetes.py` — CBP/CDC): eligibility requires a diagnosis on file
  (`Member.conditions`), not just age/sex, and the reading itself can trigger a
  safety flag (BP crisis range) independent of numerator status.

A tenant elects which measures are active (`TenantMeasureConfig`); adding
another one means writing one more module and registering it in
`measures/__init__.py` — no changes to tenant, member, or outreach code.
Pediatric measures (Childhood Immunization Status, Well-Child Visits) are a
fourth shape not yet built — see `docs/HEDIS_COMPLIANCE.md` §8 for why they
need a guardian/dependent relationship first.

## Before production

- [ ] Clinical sign-off on thresholds/weights/safety floors — see `docs/HEDIS_COMPLIANCE.md`
- [ ] HIPAA controls (BAA, access review, audit log retention) — see `docs/SECURITY_HIPAA.md`
- [ ] Real roster ingestion from the payer's eligibility feed (currently a simple bulk-create API)
- [ ] AWS infra actually applied + SES/SMS sender identities verified — see `docs/DEPLOYMENT.md`
- [ ] Claims-based or supplemental-data loop closure for measures HEDIS can't credit from self-report alone
