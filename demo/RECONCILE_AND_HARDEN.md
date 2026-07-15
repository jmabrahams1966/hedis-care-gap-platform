# cogai-payor — reconcile GitHub with production + remove the weak default

**Run this on the Mac that holds the REAL source** (`JMA-MBP-2026` / user `johnmabrahams`) —
the machine you built and deployed the `hedis-care-gap` image from. This Mac's
clone (`Desktop/Claude/hedis-care-gap-platform`) is **stale** and must not be pushed.

## Why
The GitHub repo `github.com/jmabrahams1966/hedis-care-gap-platform` (last commit
`b022f6c`, 2026-07-06) is **behind production**. The deployed image (2026-07-08)
contains code that is NOT on GitHub, confirmed against the live system:
- PII field-encryption (`PII_ENCRYPTION_KEY`, `KMS_KEY_ARN`)
- Audit-log archiving to S3 (`AUDIT_ARCHIVE_BUCKET`)
- Extra HEDIS measures: **Diabetes Eye Exam, Diabetes Kidney Health, Cervical Cancer**
- A `/security` staff page
- `app_base_url` derived from the first CORS origin (magic-link fix)

Until GitHub matches prod, anyone (including an automated deploy) who builds from
GitHub will **regress production** — stripping PHI encryption + audit logging off a
HIPAA app — and reintroduce the `changeme123` default. That's the risk we're closing.

## Item 3 — push the real source to GitHub

```bash
# 1. Find the real source on this Mac (the one with the newer code):
grep -rl "PII_ENCRYPTION_KEY\|cervical_cancer\|audit_archive" ~ --include="*.py" 2>/dev/null \
  | grep -i hedis | head
#   -> cd into that project's root (it should also contain infra/terraform.tfvars)

# 2. Confirm it's the real one and ahead of GitHub:
git status
git log --oneline -5
ls backend/app/measures/            # expect cervical_cancer.py, diabetes_eye_exam.py, etc.
grep -rl "PII_ENCRYPTION_KEY" backend/app | head   # expect hits

# 3. Point at the GitHub repo (if the remote isn't already set):
git remote -v
#   if needed: git remote add origin https://github.com/jmabrahams1966/hedis-care-gap-platform.git

# 4. Push on a branch and open a PR (safer than pushing straight to main):
git checkout -b reconcile/deployed-source
git add -A && git commit -m "Reconcile GitHub with deployed production code (PII encryption, audit archive, added measures)"
git push -u origin reconcile/deployed-source
gh pr create --fill        # or open the PR in the browser
```

## Item 4 — remove the `changeme123` default (do it in the SAME branch, before pushing)

In `backend/app/seed.py`, the three seeded staff accounts hardcode the password:

```python
password_hash=hash_password("changeme123"),   # x3: superadmin / payer admin / care manager
```

Replace the literal with an env-driven value that has **no usable default**, so a
deploy can never silently ship a known password:

```python
# backend/app/config.py  (Settings)
demo_staff_password: str = ""     # must be set explicitly to seed staff

# backend/app/seed.py  (top of seed_demo_tenant, after the dev_mode/seed_demo gate)
if not settings.demo_staff_password:
    raise RuntimeError("Refusing to seed staff without DEMO_STAFF_PASSWORD set")
# then, for each StaffUser:
password_hash=hash_password(settings.demo_staff_password),
```

Notes:
- **Production is already safe** — it runs `DEV_MODE=false`, so the seed never runs,
  and its superadmin (`superadmin@cogai-payor.com`) was bootstrapped with a strong
  password. This change is about the *repo* / future redeploys, not the live box.
- After merging, if you ever redeploy, set `DEMO_STAFF_PASSWORD` (or don't seed).

## Item 5 — FIX: magic-link verify returns 401 (member check-in is broken)

**Symptom (observed on prod 2026-07-14):** a member opens the emailed check-in
link and gets "Link is invalid or expired." Network shows
`POST /api/auth/member/verify → 401`. The single-use token is being consumed
before the member's own click completes. Two likely causes (fix both):

1. **Email security link-scanning pre-consumes the token.** `nybrainspine.com`
   is Microsoft 365; Defender/Safe Links prefetches & can headless-render links
   to scan them, firing the verify call and spending the single-use token before
   the member clicks. This is the #1 suspect for a link that's dead on arrival.
2. **The `/verify` page fires verify twice** (effect-on-mount + button click, or
   a double-submit). First call 200 (consumes token), second 401, UI shows the error.

**Recommended fix (defeats both), in the real source on this Mac:**
- Backend (`app/routers/auth.py::verify_magic_link`): stop treating the token as
  hard single-use-on-first-hit. Either (a) allow the same token to be exchanged
  repeatedly within its TTL, or (b) mark it `used` only once a member SESSION is
  actually minted AND add a short grace window so a scanner's hit doesn't lock
  out the real user. Prefer issuing the session cookie/JWT idempotently for the
  same valid token within the TTL.
- Frontend (`/verify` page): fire the verify request exactly once — guard the
  effect / disable the button on click / de-dupe in-flight requests — and only
  show "invalid" after a genuine failure, not a duplicate.
- Consider lengthening `magic_ttl_minutes` slightly and adding a "request a new
  link" button on the error screen.

Until this ships, the member email check-in is unreliable for M365 inboxes; demo
the member flow with a non-M365 address, or pre-populate screenings via the
backend (see `demo/submit_safety_screening.sh`).

## Item 6 — FIX: expired session renders empty screens instead of redirecting to login

**Symptom (observed on prod 2026-07-15, during a smoke test).** After a staff JWT
expires (`jwt_ttl_hours`, ~12h), returning to the app shows the care-gap queue —
and every filter, and the superadmin tenant list — as **empty** ("Nothing here —
nice work."), which looks alarmingly like **data loss**. It is not: the data is
intact (verified 9 members / 30 gaps for usfhp-svmc directly in the DB). The real
cause is that the expired token makes the API return **401**, and the frontend
**renders empty lists instead of redirecting to login**. That's a genuine
error-handling bug — misleading, and a support-call generator.

**Recommended fix (frontend, in the real source on this Mac):**
- In the shared API client (`frontend/src/lib/api.ts`), add a **global 401
  handler**: on any `401`, clear the stored session (token/staff context) and
  redirect to the login screen (`/login`, or `/` once Feature F's unified login
  lands). Optionally show a "Your session expired — please sign in again" notice.
- Ensure list/query components distinguish **"empty result"** from **"auth
  error"** — an auth error should never render the friendly empty state.
- Consider a token-refresh or a longer `jwt_ttl_hours` for staff to reduce how
  often this bites during a working day.

This pairs naturally with **Feature F (unified login)** — both touch the auth/entry
frontend. See `docs/superpowers/specs/2026-07-15-unified-login-design.md`.

## Verify when done
- On GitHub, confirm `backend/app/measures/cervical_cancer.py` and a
  `PII_ENCRYPTION_KEY` reference now exist on the default branch.
- Grep the repo for `changeme123` → should return nothing.
- Re-test the emailed check-in link from an M365 inbox end-to-end (verify → PHQ-9 → submit).
- Force a `401` (let a staff token expire, or clear it) → confirm the app **redirects to login**, not an empty "Nothing here" screen.
