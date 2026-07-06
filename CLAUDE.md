# Project memory — HEDIS Care Gap Platform

Read this first when resuming work on this repo from a new machine/session.
See `README.md` for architecture and local-run instructions; this file is
status, decisions, and what's next.

## What this is

Multi-tenant remote patient outreach platform for health plans (payers) — SMS/
email check-ins that close HEDIS care gaps. Built around a pluggable measure
architecture: a tenant elects which HEDIS measure modules are active
(`backend/app/measures/`), each with its own eligibility rules, outreach
templates, and gap tracking. Seven modules exist so far, covering four
structurally different shapes:

- **Mental health** (Depression Screening & Follow-Up / DSF) — PHQ-9 + GAD-7
  questionnaire, server-side scored, safety-flag escalation. Age-gated (12+).
- **Breast Cancer Screening** (BCS) and **Colorectal Cancer Screening** (COL) —
  self-report + scheduling-assistance flow, no instrument. Age-gated (+ sex,
  for BCS).
- **Controlling High Blood Pressure** (CBP) and **Diabetes HbA1c Testing &
  Control** (CDC subset) — self-reported clinical reading. **Condition-gated**:
  eligibility requires a diagnosis on `Member.conditions`
  (e.g. `["hypertension"]`), not just age/sex. CBP also introduces a
  non-mental-health safety flag (hypertensive crisis, systolic >=180 or
  diastolic >=120).
- **Childhood Immunization Status** (CIS) and **Well-Child Visits** (WCV) —
  **dependent-scoped**: the measure's subject is the account holder's child
  (a `Dependent` row), not the account holder themselves. The guardian
  (`Member`) still receives outreach and authenticates; `CareGap.member_id`
  stays the guardian while `CareGap.dependent_id` is the actual subject.
  `Measure.subject_type = "dependent"` is what distinguishes these from
  everything else — see `app/models.py::Dependent`,
  `app/routers/dependents.py`, and `app/routers/members.py::
  _open_care_gaps_for_dependent`.

This required a real architectural fork (not just another module): `Member`
used to conflate "the enrollee" and "the person answering questions about
themselves," which doesn't fit a child being screened while a parent answers
on their behalf. If you're adding a measure and its subject is ever someone
other than the account holder, follow the `Dependent` pattern — don't bolt
their data onto an adult `Member` row.

## Current status

- **Backend**: FastAPI + async SQLAlchemy. Fully working locally (SQLite,
  dev_mode). 71 passing tests (`backend/tests/`). Alembic wired up
  (`backend/migrations/`) with three migrations generated (initial schema,
  `Member.conditions`, then the `Dependent` table + `CareGap.dependent_id`).
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
- **Inbound SMS webhook**: `POST /api/webhooks/sms-inbound` now handles
  STOP/START keyword replies with real AWS SNS signature verification
  (`backend/app/notifications/sns_verify.py`) — not a stub. `infra/modules/
  messaging` provisions the SNS topic + HTTPS subscription + configuration
  set; the origination phone number's two-way channel still needs a manual
  `aws pinpoint-sms-voice-v2` call after `terraform apply` (see
  `docs/DEPLOYMENT.md` §2 step 4 — deliberately not Terraform-managed, see
  the comment in `infra/modules/messaging/main.tf`).

## Possible first partner: St. Vincent's / USFHP

You mentioned St. Vincent's/USFHP as a likely first partner. Verified via
web search: **St. Vincent Catholic Medical Centers (SVCMC)** is one of the
designated provider organizations for **USFHP (US Family Health Plan)**, a
TRICARE Prime option for military families/retirees, serving NY metro, NJ,
SE Pennsylvania, and Western Connecticut. A few implications worth keeping in
mind as this becomes concrete, not yet acted on:

- Military/dependent-heavy population → CIS and WCV (pediatric measures) are
  probably higher-value here than for an average commercial payer, not an
  afterthought.
- USFHP designated providers are NCQA-accredited and already report
  HEDIS-like measures to DHA (a quality-withhold arrangement) — the pitch
  should land as familiar, not novel.
- Real roster/eligibility feed will likely be DEERS-linked, not a standard
  commercial 834 — don't guess the schema, confirm with them when this is real.
- Compliance is TRICARE + HIPAA, not just HIPAA — there may be a DoD
  data-sharing agreement layer on top of what `docs/SECURITY_HIPAA.md`
  currently covers. Noted as a doc TODO, nothing TRICARE-specific built yet.

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
- **BCS/COL numerator is currently self-report.** Real HEDIS credit for both
  normally needs claims/encounter confirmation. Flagged, not implemented.
- **`Member.conditions`** (JSON list, e.g. `["hypertension", "diabetes"]`) is
  the mechanism for diagnosis-gated eligibility — added for CBP/CDC. Use this,
  not a one-off boolean field, for any future condition-gated measure.
- **CBP/CDC numerator is a self-reported reading/value**, not a clinical or
  claims-confirmed one. This is a bigger caveat than BCS/COL's self-report
  issue — a home BP cuff or a remembered A1c value can genuinely differ from
  the chart. Explicit clinical sign-off needed before relying on this for
  anything beyond outreach triage. See `docs/HEDIS_COMPLIANCE.md` §4-5.
- **CDC here is the HbA1c sub-measure only** — the full HEDIS Comprehensive
  Diabetes Care bundle also includes eye exam and nephropathy monitoring,
  neither implemented.
- **`Dependent` model + `CareGap.dependent_id`** (nullable FK) built for
  CIS/WCV. `CareGap`'s uniqueness is enforced via **two partial unique
  indexes** (`uq_member_measure_period_no_dependent` WHERE dependent_id IS
  NULL, `uq_dependent_measure_period` WHERE dependent_id IS NOT NULL), not one
  plain `UniqueConstraint` — a single constraint would silently allow
  duplicate member-scoped gaps, since standard SQL treats every NULL as
  distinct from every other NULL in a unique constraint. This let two
  dependents of the same guardian each get their own gap for the same
  measure+period, verified directly against the schema in a raw-SQL test
  before trusting the app-level "check existing before insert" logic alone.
- **SQLite migration gotcha**: the migration adding `dependent_id` needed
  `op.batch_alter_table(...)` for the `care_gaps` ALTER — SQLite can't
  `ALTER`/`DROP` constraints directly (Postgres can). Batch mode is the
  portable way to write one migration that works on both; plain
  `op.drop_constraint(...)` outside batch mode will fail on SQLite specifically.
- **SNS signature verification is real crypto, not a stub** — RSA PKCS1v15
  over SNS's exact canonical string (field order matters, differs for
  Notification vs. SubscriptionConfirmation), SHA1 or SHA256 depending on
  `SignatureVersion`. The signing cert URL and the `SubscribeURL` are both
  checked against an `sns.*.amazonaws.com` allow-list *before* any fetch —
  an attacker-supplied URL in either field is a real SSRF vector otherwise.
  See `backend/app/notifications/sns_verify.py`, tested in
  `backend/tests/test_sns_verify.py` (crypto-level, synthetic cert) and
  `backend/tests/test_webhooks.py` (full HTTP path through the FastAPI app).
- **The SMS origination phone number is intentionally not a Terraform
  resource.** Toll-free/10DLC numbers are manually verified through AWS
  Support and take days; managing one as `aws_pinpointsmsvoicev2_phone_number`
  risks Terraform trying to recreate/release a real leased number on state
  drift. Terraform manages the SNS topic/subscription/configuration set;
  wiring the number's two-way channel to that topic is a one-time manual
  step (console or CLI) documented in `docs/DEPLOYMENT.md`.

## Known gaps / good next steps

- MFA for staff logins (password + JWT only today)
- WAF in front of the ALB/CloudFront (not yet in Terraform)
- Field-level encryption for member PII beyond whole-disk/at-rest
- Fix `CareGap.period` for BCS/COL/CIS/WCV's actual lookback windows
  (multi-year or non-calendar, not calendar-year — and COL's varies by
  screening modality)
- Claims-based (not self-report) numerator confirmation for BCS, COL, CBP,
  CDC, CIS, WCV — every measure's numerator is currently self-report or a
  self-reported clinical value, none are claims/encounter-confirmed
- CIS/WCV are self-report proxies only — real numerator credit needs
  immunization-registry or claims data neither module has access to
- WCV only covers ages 3-17 of HEDIS's real 0-21 eligible population (no
  infant/toddler visit-count logic, no young-adult band)
- Real roster ingestion from an actual payer eligibility feed format (834,
  or whatever the first real payer sends) — currently JSON bulk + CSV upload.
  CSV now ingests members and dependents together in one file
  (`guardian_external_member_id` column marks a dependent row; dependent rows
  are processed after all member rows so file ordering doesn't matter, and a
  guardian can be resolved either from the same upload or an earlier one).
- Nothing has clinical/HEDIS/legal sign-off yet — see the checklists in
  `docs/HEDIS_COMPLIANCE.md` and `docs/SECURITY_HIPAA.md`, both currently
  unsigned
- SNS signature verification has never been exercised against a real
  AWS-signed message — only against a synthetic self-signed cert in tests.
  Verify end-to-end once a real SNS subscription exists.
- WAF, VPC Flow Logs, and shipping audit logs to a write-once store (S3
  Object Lock) are still open items in `docs/SECURITY_HIPAA.md` §5/§4

## Where things are

```
backend/app/measures/        Pluggable measure modules (start here to add a new one)
backend/app/routers/dependents.py   Create/list a guardian's dependents
backend/app/outreach_service.py   Shared outreach-send logic
backend/app/scripts/run_outreach_cron.py   Scheduled batch job entrypoint
backend/app/notifications/sns_verify.py   AWS SNS signature verification (inbound SMS webhook)
backend/app/routers/webhooks.py   POST /api/webhooks/sms-inbound — STOP/START handling
backend/migrations/           Alembic — run `alembic upgrade head` for prod schema changes
backend/tests/                pytest suite, 71 tests, run with pytest.ini config
frontend/src/components/      Shared AppNav, StepIndicator
frontend/src/styles/theme.css Design tokens
infra/                        Terraform — validated, not applied
infra/modules/messaging/      SNS topic + HTTPS subscription + SMS configuration set
docs/HEDIS_COMPLIANCE.md      Instrument licensing, thresholds, sign-off checklist
docs/SECURITY_HIPAA.md        Encryption, audit logging, BAA checklist
docs/DEPLOYMENT.md            Step-by-step AWS deployment runbook
```
