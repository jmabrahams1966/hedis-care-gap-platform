# Unified Single-Screen Login — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **PREREQUISITE #0.** GitHub is behind production — implement in the real source on `JMA-MBP-2026` after reconciling (`demo/RECONCILE_AND_HARDEN.md`). Confirm the actual component paths/names against the real source (the deployed frontend is ahead of the clone). This is **frontend-only** — no backend/endpoint/RBAC change. Verification is `npx tsc --noEmit` + browser checks (this repo has no frontend unit-test runner; match the existing pattern).

**Goal:** One `/` sign-in screen with a Member / Nurse Manager / Admin role selector that swaps the form, replacing the split landing + separate staff-login page, reusing existing auth endpoints.

**Architecture:** Extract the two existing forms into `MemberSignInForm` + `StaffSignInForm`, then compose them under a `RoleSelector` in a new `UnifiedLogin` page; rewire routes.

**Tech Stack:** React 18 + TS + Vite, react-router-dom.

**Reference spec:** `docs/superpowers/specs/2026-07-15-unified-login-design.md`

---

### Task 1: Extract `MemberSignInForm` and `StaffSignInForm`

**Files:**
- Create: `frontend/src/components/auth/MemberSignInForm.tsx`, `frontend/src/components/auth/StaffSignInForm.tsx`
- Modify: `frontend/src/pages/member/MemberEntry.tsx`, `frontend/src/pages/StaffLogin.tsx` (render the extracted components)

- [ ] **Step 1** — Move the member ID+DOB form (and its `POST /api/auth/member/magic` → "check your email" state) out of `MemberEntry` into `MemberSignInForm` (self-contained; no props needed, or accept an optional `onSent` callback). `MemberEntry` now renders `<MemberSignInForm/>`.

- [ ] **Step 2** — Move the email+password form (and its `POST /api/auth/staff/login` + post-login `navigate` by role) out of `StaffLogin` into `StaffSignInForm`. `StaffLogin` now renders `<StaffSignInForm/>`.

- [ ] **Step 3** — Verify no behavior change: `cd frontend && npx tsc --noEmit`; run the app; confirm `/start` (member) and `/login` (staff) still work exactly as before. **Commit.**

```bash
git add frontend/src/components/auth/ frontend/src/pages/member/MemberEntry.tsx frontend/src/pages/StaffLogin.tsx
git commit -m "refactor(auth): extract MemberSignInForm + StaffSignInForm (no behavior change)"
```

### Task 2: `RoleSelector` + `UnifiedLogin`

**Files:**
- Create: `frontend/src/components/auth/RoleSelector.tsx`, `frontend/src/pages/UnifiedLogin.tsx`
- Reference the layout: live cogai-campus.com / `Desktop/Claude/CogAI-College-Site` (three cards + one form).

- [ ] **Step 1** — `RoleSelector.tsx`: three cards (`member` | `nurse_manager` | `admin`) with icon + label; `value` + `onChange`. Cards are accessible buttons; the selected one is highlighted.

```tsx
// frontend/src/components/auth/RoleSelector.tsx
export type LoginRole = "member" | "nurse_manager" | "admin";
const CARDS: { role: LoginRole; label: string; icon: string }[] = [
  { role: "member", label: "Member", icon: "🧑" },
  { role: "nurse_manager", label: "Nurse Manager", icon: "🩺" },
  { role: "admin", label: "Admin", icon: "📊" },
];
export function RoleSelector({ value, onChange }: { value: LoginRole; onChange: (r: LoginRole) => void }) {
  return (
    <div className="role-cards" role="tablist">
      {CARDS.map((c) => (
        <button key={c.role} role="tab" aria-selected={value === c.role}
                className={`role-card ${value === c.role ? "selected" : ""}`}
                onClick={() => onChange(c.role)}>
          <span className="role-icon">{c.icon}</span><span>{c.label}</span>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2** — `UnifiedLogin.tsx`: holds `role` state (default `"member"`); renders `<RoleSelector/>` + the matching form — `<MemberSignInForm/>` for `member`, `<StaffSignInForm/>` for `nurse_manager` and `admin` (same component; the card is a hint). Focus the first field on card change.

```tsx
// frontend/src/pages/UnifiedLogin.tsx (core)
const [role, setRole] = useState<LoginRole>("member");
return (
  <div className="unified-login">
    <h2>Sign in</h2>
    <RoleSelector value={role} onChange={setRole} />
    {role === "member" ? <MemberSignInForm /> : <StaffSignInForm />}
  </div>
);
```

- [ ] **Step 3** — `npx tsc --noEmit`; browser: cards render, switching swaps the form. **Commit.**

```bash
git add frontend/src/components/auth/RoleSelector.tsx frontend/src/pages/UnifiedLogin.tsx
git commit -m "feat(auth): RoleSelector + UnifiedLogin page"
```

### Task 3: Route wiring

**Files:** Modify `frontend/src/App.tsx` (routes) and remove/redirect the old landing.

- [ ] **Step 1** — Make `/` render `<UnifiedLogin/>` (replace the two-card `Landing`). Keep `/verify` exactly as-is. Add redirects: `/login` → `/` and `/start` → `/` (`<Navigate to="/" replace />`). Preserve the existing "authenticated → role home" guard on `/`.

- [ ] **Step 2** — `npx tsc --noEmit`; browser: hitting `/login` or `/start` lands on `/`; an authenticated staff user hitting `/` is redirected to their home. **Commit.**

```bash
git add frontend/src/App.tsx
git commit -m "feat(auth): / is the unified login; /login + /start redirect; /verify unchanged"
```

### Task 4: End-to-end browser verification + polish

- [ ] **Step 1** — Member path: `/` → Member card → ID `USF-105` + DOB → magic email sends → open the emailed `/verify` link → lands in the check-in. (On prod this exercises the known verify-401 issue separately — that's Feature D/reconcile scope, not this feature.)
- [ ] **Step 2** — Nurse Manager path: Nurse Manager card → care-manager creds → lands on `/queue`.
- [ ] **Step 3** — Admin path: Admin card → payer-admin creds → lands on measures/overview. Confirm a mismatched card (Admin card + care-manager creds) still routes to the care-manager home (role from account).
- [ ] **Step 4** — Responsive/dark-mode pass on the card layout. **Commit** any polish.

---

## Self-review checklist (done)
- **Spec coverage:** extracted forms (T1), RoleSelector + UnifiedLogin (T2), routing incl. `/verify` untouched + `/login`/`/start` redirects (T3), all three paths verified + mismatched-card behavior (T4). No backend change, per spec.
- **Placeholders:** none; the only "confirm against real source" note is the component paths (deployed frontend is ahead of the clone) — inherent to the reconcile-first constraint, not a gap.
- **Type consistency:** `LoginRole` (`member|nurse_manager|admin`) used consistently in `RoleSelector` and `UnifiedLogin`; the two staff roles both render `StaffSignInForm` (post-login routing keys off the API's returned account role, not `LoginRole`).
