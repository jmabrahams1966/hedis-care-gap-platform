# Plan Verification vs Real Source (2026-07-15)

The A–F specs/plans were authored against a **stale clone**. After the real
production source was reconciled to GitHub `main` (commit `4db2a98`), each plan
was checked against the actual code. This is the authoritative delta.

## Verdicts

| Plan | Verdict | Key corrections before building |
|---|---|---|
| **A · Quality Overview** | ✅ NEW — build it | `reports.py` has only `GET /hedis` (no `/overview`). `require_role(*roles)` **does** exist in `deps.py` — the plan's usage is correct. Note the real source has **15 measures** (incl. PDC trio, PPC prenatal/postpartum, eye_exam, kidney_health, cervical); the overview aggregation iterates all — fine. Consider reusing `/hedis`'s aggregation to avoid duplication. `MeasureSnapshot` (v1.1) does not exist — build as planned. |
| **B · Care-management workspace** | ✅ NEW — build it | `CaseNote` exists but its text field is **`note`** (not `body`), fields: `id, care_gap_id, author_id, note, created_at`. Add `note_type` to it. `CarePlanGoal / CareTask / SafetyPlan / EscalationStep` — none exist, build as planned. Safety ties to the existing `CareGap.safety_flag`. `require_role` confirmed. |
| **C1 · Outreach cadence** | ✅ NEW — build it | No `OutreachSequence/Step/Enrollment` tables. Reuses `outreach_service`, `OutreachAttempt`, `run_outreach_cron` — all present. Build as written. |
| **C2 · Pharmacy / PDC** | ⛔ **ALREADY BUILT — DO NOT BUILD** | Real implementation exists: `models.MedicationFill` (= plan's "FillRecord"; `drug_class String(32)`, `days_supply`), `measures/pdc.py` + `pdc_service.py` (`recompute_pdc_for_member`), `measures/medication_adherence.py`, `routers/medications.py` (`POST /api/medications/fills/bulk`, `GET /api/medications/pdc/{external_member_id}`), migration `b1f7c3d9e2a4_add_medication_fills_table`, `test_pdc.py`, `test_medications_flow.py`. Measures: `pdc_diabetes`, `pdc_hypertension` (plan called it `pdc_ras`), `pdc_statins`; drug classes `diabetes / rasa / statins`. **Use the C2 spec/plan as reference only.** |
| **D · Secure messaging** | ✅ NEW — build it | No `Conversation/Message` tables, no messaging router. Reuses `webhooks` (STOP/START present), magic-link, `outreach_service`. Build as written. |
| **E · KaveraChat AI** | ✅ NEW — build it, with a fix | ⚠️ **There is NO existing Bedrock/Claude/Anthropic client in the codebase** (grep found nothing). The plan said "reuse the app's existing Bedrock client" — that's wrong; **Feature E must ADD the Bedrock integration** (client + IAM `bedrock:InvokeModel` on the ECS task role). `AiInteraction` table is new. Everything else stands. |
| **F · Unified login** | ✅ NEW — build it, with a fix | ⚠️ `StaffLogin.tsx` now implements a **two-step MFA flow** (`onSubmitPassword` → if `mfa_required` → `onSubmitCode` against `/api/auth/staff/mfa/verify`). The plan's `StaffSignInForm` extraction must **preserve the full MFA flow**, not just email+password. `Landing.tsx` (two-card) + `MemberEntry.tsx` exist to consolidate. Endpoints unchanged. |

## Harden items (`RECONCILE_AND_HARDEN.md`) status vs real code

- **§4 `changeme123` default** — STILL present (`seed.py` hardcodes it, gated on `dev_mode`). Fix as written.
- **§5 verify-401** — **partially addressed**: `config.magic_ttl_minutes` is already `10080` (7 days), and `auth._deliver_magic_link` already degrades SMS→email gracefully. The **single-use-token-consumed-by-prefetch** aspect still needs review of the member `verify` endpoint (make it idempotent within the TTL, or don't mark used until a session is minted).
- **§6 401-redirect** — **needed**: `frontend/src/lib/api.ts` throws `ApiError(status,…)` but has **no 401 handler** → confirms the expired-session-shows-empty bug. Add the global 401 → redirect-to-login.

## Bonus: features already built that were NOT in the A–F design set

Discovered in the reconciled source (treat as done): **PPC / maternity**
(`prenatal_postpartum.py`, `ppc_service.py`, `routers/maternity.py`,
`PregnancyEpisode`), **HEDIS exclusions** (`exclusions.py`, `MemberExclusion`,
`apply_exclusions_for_member`), **staff MFA + account lockout**, **PII field
encryption** (`crypto.py`), **audit archive** (`audit_archive.py` + `infra/modules/audit`),
**WAF** (`infra/modules/waf`), **Security page** (`frontend/.../Security.tsx`),
and the **eye_exam / kidney_health** diabetes measures.

## Recommended build order (revised)

**F → A → B → C1 → D → E.** (C2 and MFA already done.) F is lowest-risk
(frontend-only, no backend change) and gives the demo the requested one-screen login.
