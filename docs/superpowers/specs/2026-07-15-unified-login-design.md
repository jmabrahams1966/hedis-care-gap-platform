# Design — Unified Single-Screen Login (Feature F)

**Date:** 2026-07-15
**Product:** cogai-payor / HEDIS Care Gap Platform
**Status:** Approved design, pending implementation plan
**Implement in:** the real source on `JMA-MBP-2026` (GitHub is behind prod — reconcile first).

## 1. Purpose

One sign-in screen — modeled on CogAi Campus — where **Member / Nurse Manager / Admin** all
start from a role selector, replacing today's split landing ("I'm a member" vs "I'm plan staff")
and the separate staff-login page. Frontend-only; reuses existing auth endpoints unchanged.

## 2. Goals & non-goals

**Goals**
- A single `UnifiedLogin` page: three role cards (Member / Nurse Manager / Admin) that **swap the
  form** below them.
- Member → ID + DOB → magic link; Nurse Manager / Admin → email + password.
- No backend/auth change; post-login routing unchanged (account role governs).

**Non-goals**
- Any backend, endpoint, or role-model change.
- Merging the two staff roles' auth (they already share `/staff/login`; the cards are cosmetic hints).
- i18n work (EN/ES) — out of scope here; note only.

## 3. Architecture

- **`UnifiedLogin`** page (React) holds `selectedRole` state and renders a **`RoleSelector`**
  (three cards) + the matching form.
- **`MemberSignInForm`** — extracted from the existing `MemberEntry`: Member ID + DOB →
  `POST /api/auth/member/magic` → "check your email". Unchanged logic.
- **`StaffSignInForm`** — extracted from the existing `StaffLogin`: email + password →
  `POST /api/auth/staff/login` → on success, route by the **returned account role**
  (care_manager → `/queue`, payer_admin → measures/overview, super_admin → tenants). Used by both
  the Nurse Manager and Admin cards (identical form; the card is a presentational hint).

Extracting the two forms as focused components (from `MemberEntry`/`StaffLogin`) is the only
refactor — it keeps each form testable and lets `UnifiedLogin` compose them without duplicating logic.

## 4. Routing

- **`/` becomes the unified login** (replaces the two-card landing).
- Keep **`/verify`** exactly as-is (the emailed magic-link return target — untouched).
- **`/login`** and **`/start`** → redirect to `/` (back-compat for any bookmarks / old links).
- Authenticated users hitting `/` are redirected to their role's home (existing guard behavior).

## 5. Behavior / data flow

1. Land on `/` → role selector, Member preselected (most common visitor).
2. Pick a card → form swaps (no navigation).
3. **Member:** ID + DOB → magic endpoint → "check your email" panel (existing copy).
4. **Nurse Manager / Admin:** email + password → staff login → route by returned role. A wrong-role
   guess is harmless: the account's real role governs; if a user picked "Admin" but the account is
   care_manager, they still land on the care-manager home.
5. Errors (bad password, no member match) show inline per the existing forms.

## 6. Non-functional

- Reuses existing endpoints → no new API surface, no new RBAC.
- Accessibility: cards are real buttons/tabs with labels; form focus moves on card select.
- Visual language matches the app (and echoes CogAi Campus's card layout).

## 7. Open questions

1. **Landing copy / imagery** — reuse Campus's tone ("A private space for how you're doing") or a
   HEDIS/plan-appropriate line? (Design detail, not blocking.)
2. **ES localization** — Campus ships EN/ES; USFHP may want it. Deferred (note only).

## 8. Sequencing

1. Extract `MemberSignInForm` + `StaffSignInForm` from `MemberEntry`/`StaffLogin` (no behavior change).
2. Build `RoleSelector` + `UnifiedLogin` composing them.
3. Route wiring: `/` = unified login; `/login` + `/start` → redirect; `/verify` untouched.
4. Browser-verify all three paths + polish.

## 9. Success criteria

- `/` shows three cards; Member preselected.
- Member ID + DOB triggers the magic email; the emailed `/verify` link still works end-to-end.
- Nurse-manager and admin credentials each sign in from the same screen and land on the correct
  role home; a mismatched card choice still routes by the real account role.
- `/login` and `/start` redirect to `/`; no separate staff-login page remains.
