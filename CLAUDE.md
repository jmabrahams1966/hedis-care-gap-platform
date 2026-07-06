# Project memory — HEDIS Care Gap Platform

Read this first when resuming work on this repo from a new machine/session.
See `README.md` for architecture and local-run instructions; this file is
status, decisions, and what's next.

## What this is

Multi-tenant remote patient outreach platform for health plans (payers) — SMS/
email check-ins that close HEDIS care gaps. Built around a pluggable measure
architecture: a tenant elects which HEDIS measure modules are active
(`backend/app/measures/`), each with its own eligibility rules, outreach
templates, and gap tracking. Two modules exist so far:

- **Mental health** (Depression Screening & Follow-Up / DSF) — PHQ-9 + GAD-7
  questionnaire, server-side scored, safety-flag escalation
- **Breast Cancer Screening** (BCS) — self-report + scheduling-assistance
  flow, structurally different from DSF (proves the architecture generalizes)

## Current status

- **Backend**: FastAPI + async SQLAlchemy. Fully working locally (SQLite,
  dev_mode). 22 passing tests (`backend/tests/`). Alembic wired up
  (`backend/migrations/`) with an initial migration already generated.
- **Frontend**: React + TS + Vite. Redesigned UI (design system, shared nav,
  step indicators) as of the last commit. Verified in-browser across every
  page/role at desktop + mobile widths.
- **Infra**: Terraform for the full AWS stack is written and **validated**
  (`terraform validate` and `terraform plan` both pass — see "Terraform
  validation" below) but **never applied**. No AWS resources exist yet.
- **Domain**: `cogai-payor.com` reserved in Route 53. `infra/terraform.tfvars`
  has the real domain wired in but is gitignored (per-deployment values,
  not committed) — **you'll need to recreate it locally**, see
  "Recreating terraform.tfvars" below.

## Blocker: AWS apply has not happened

Nothing has been provisioned on AWS yet. Two things stood in the way of doing
it from the remote session, neither of which apply to your other computer:

1. That session's AWS credentials were placeholders (`InvalidClientTokenId`),
   not real ones.
2. That session's network policy blocks `registry.terraform.io`; a local
   provider mirror was set up there as a workaround (see below) but that's a
   sandbox-specific workaround, not something you need to replicate locally
   assuming your machine has normal internet access.

**On your computer, with real AWS CLI credentials configured, `terraform
apply` should just work.** Follow `docs/DEPLOYMENT.md` in order:
1. Verify SES sending identity for `cogai-payor.com`
2. Push the backend image to ECR
3. `terraform init && terraform plan && terraform apply` in `infra/`
4. Run the Alembic migration against the new Aurora cluster
5. Deploy the frontend to S3/CloudFront
6. Request the SMS origination number (slow — start early, works without it via email in the meantime)

### Recreating terraform.tfvars

`infra/terraform.tfvars` is gitignored. Recreate it with:

```hcl
domain_name   = "cogai-payor.com"
app_subdomain = "app"
api_subdomain = "api"
create_hosted_zone = false   # Route 53 "Registered domains" already creates the zone

container_image = ""          # fill in after building + pushing to ECR (DEPLOYMENT.md step 2)
ses_from_email        = "no-reply@app.cogai-payor.com"
sms_origination_phone = ""    # fill in once AWS approves your SMS number

db_min_capacity = 0.5
db_max_capacity = 4
desired_count   = 2
outreach_cron_schedule = "rate(1 day)"
```

### Terraform validation (already done, in a sandboxed session)

`terraform init`, `validate`, and `plan` all passed cleanly against this
domain — `plan` even correctly resolved `api_url = https://api.cogai-payor.com`
and `app_url = https://app.cogai-payor.com` before failing solely on
`InvalidClientTokenId`. That means the HCL itself is confirmed correct; the
only remaining step is running `apply` with real credentials. You should not
need to debug the Terraform code itself — if `apply` fails, it's most likely
a permissions/quota issue in the AWS account, not a bug in `infra/`.

## Key decisions made along the way

- **Generic `responses` dict** for screening submissions
  (`POST /api/screenings`), not per-measure fields — each `Measure` module
  interprets its own payload shape. This was a real refactor forced by adding
  BCS (see `backend/app/measures/base.py`).
- **`numerator_met` bug**: was hardcoded `true` before the BCS module exposed
  that it needed to come from the measure's actual evaluation. Fixed.
- **Care-gap exclusions require a reason** (`GapStatusUpdate.reason`) —
  matches what a HEDIS auditor will ask for.
- **Outreach batch logic** lives in `backend/app/outreach_service.py`, shared
  between the authenticated per-tenant API endpoint
  (`POST /api/outreach/run-batch`) and the scheduled cron entrypoint
  (`backend/app/scripts/run_outreach_cron.py`, run by Terraform's
  EventBridge Scheduler + dedicated ECS task in `infra/modules/ecs`).
- **CareGap.period is a calendar year** — fine for DSF, **wrong for BCS**
  (which needs a rolling ~27-month lookback per the real HEDIS spec). Flagged
  in `docs/HEDIS_COMPLIANCE.md` but not fixed yet — worth doing before BCS
  numbers go anywhere official.
- **BCS numerator is currently self-report.** Real HEDIS BCS credit normally
  needs claims/encounter confirmation. Flagged, not implemented.

## Known gaps / good next steps

- MFA for staff logins (password + JWT only today)
- WAF in front of the ALB/CloudFront (not yet in Terraform)
- Field-level encryption for member PII beyond whole-disk/at-rest
- Fix `CareGap.period` for BCS's actual lookback window
- Claims-based (not self-report) numerator confirmation for BCS
- Real roster ingestion from an actual payer eligibility feed format (834,
  or whatever the first real payer sends) — currently JSON bulk + CSV upload
- Nothing has clinical/HEDIS/legal sign-off yet — see the checklists in
  `docs/HEDIS_COMPLIANCE.md` and `docs/SECURITY_HIPAA.md`, both currently
  unsigned

## Where things are

```
backend/app/measures/        Pluggable measure modules (start here to add a new one)
backend/app/outreach_service.py   Shared outreach-send logic
backend/app/scripts/run_outreach_cron.py   Scheduled batch job entrypoint
backend/migrations/           Alembic — run `alembic upgrade head` for prod schema changes
backend/tests/                pytest suite, 22 tests, run with pytest.ini config
frontend/src/components/      Shared AppNav, StepIndicator
frontend/src/styles/theme.css Design tokens
infra/                        Terraform — validated, not applied
docs/HEDIS_COMPLIANCE.md      Instrument licensing, thresholds, sign-off checklist
docs/SECURITY_HIPAA.md        Encryption, audit logging, BAA checklist
docs/DEPLOYMENT.md            Step-by-step AWS deployment runbook
```
